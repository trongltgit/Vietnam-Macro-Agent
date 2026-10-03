"""
Tools for fetching official Vietnamese government reports.
Hard-coded trusted entry points + HTML extraction.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

NSO_BAI_TOP = "https://www.nso.gov.vn/bai-top/"
NSO_GIA = "https://www.nso.gov.vn/category/gia/"
NHNN_TY_GIA = "https://sbv.gov.vn/vi/t%E1%BB%B7-gi%C3%A1"
NHNN_HOME = "https://sbv.gov.vn/vi/"
NHNN_ANNUAL = "https://sbv.gov.vn/en/w/annual-report-2023"
NHNN_CPI = "https://sbv.gov.vn/vi/"  # CPI often on home / news

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; VietnamMacroAgent/1.0; "
        "+https://github.com/trongltgit/Vietnam-Macro-Agent)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}


class OfficialSourceTool:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = httpx.Client(
            headers=HEADERS,
            timeout=45.0,
            follow_redirects=True,
        )

    def close(self) -> None:
        self.client.close()

    def fetch_page(self, url: str) -> Dict[str, Any]:
        logger.info("fetch_page", url=url)
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            title = (soup.title.string or "").strip() if soup.title else ""
            for tag in soup(["script", "style", "nav", "footer", "noscript"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            text = re.sub(r"\n{3,}", "\n\n", text)

            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                full = urljoin(url, href)
                text_a = a.get_text(strip=True)
                lower = full.lower()
                item_type = "page"
                if any(ext in lower for ext in [".pdf", ".xlsx", ".xls", ".csv"]):
                    item_type = Path(full).suffix.lower() or "file"
                links.append({"url": full, "text": text_a, "type": item_type})

            return {
                "url": url,
                "title": title,
                "text": text[:20000],
                "links": links[:60],
                "status": "ok",
            }
        except Exception as e:
            logger.error("fetch_page_failed", url=url, error=str(e))
            return {"url": url, "status": "error", "error": str(e)}

    def download_file(self, url: str, subdir: str = "other") -> Dict[str, Any]:
        logger.info("download_file", url=url, subdir=subdir)
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
            cd = resp.headers.get("content-disposition", "")
            filename = None
            if "filename=" in cd:
                m = re.findall(r'filename="?([^";]+)"?', cd)
                filename = m[0] if m else None
            if not filename:
                filename = Path(url.split("?")[0]).name or f"file_{datetime.now():%Y%m%d_%H%M%S}"
            filename = re.sub(r"[^\w\.\-]", "_", filename)[:120]
            dest_dir = self.settings.raw_dir / subdir
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / filename
            dest.write_bytes(resp.content)
            return {
                "status": "ok",
                "local_path": str(dest),
                "url": url,
                "size_bytes": dest.stat().st_size,
                "filename": filename,
            }
        except Exception as e:
            logger.error("download_failed", url=url, error=str(e))
            return {"status": "error", "url": url, "error": str(e)}

    def list_nso_latest_reports(self) -> List[Dict[str, str]]:
        """Parse NSO nổi bật page for socio-economic reports."""
        page = self.fetch_page(NSO_BAI_TOP)
        reports: List[Dict[str, str]] = []
        if page.get("status") != "ok":
            return reports

        for link in page.get("links", []):
            text = (link.get("text") or "").strip()
            url = link.get("url") or ""
            low = text.lower()
            if not text or len(text) < 10:
                continue
            if any(
                k in low
                for k in [
                    "kinh tế",
                    "kinh te",
                    "xã hội",
                    "xa hoi",
                    "báo cáo",
                    "bao cao",
                    "gdp",
                    "cpi",
                    "tháng",
                    "quý",
                    "quy",
                ]
            ):
                if "nso.gov.vn" in url:
                    reports.append({"title": text, "url": url, "type": link.get("type", "page")})

        # Dedupe
        seen = set()
        unique = []
        for r in reports:
            if r["url"] not in seen:
                seen.add(r["url"])
                unique.append(r)
        return unique[:20]

    def list_nhnn_reports(self) -> List[Dict[str, str]]:
        candidates = [NHNN_ANNUAL, NHNN_HOME, "https://sbv.gov.vn/en/w/annual-report-2023"]
        reports: List[Dict[str, str]] = []
        for url in candidates:
            page = self.fetch_page(url)
            if page.get("status") != "ok":
                continue
            for link in page.get("links", []):
                text = (link.get("text") or "").lower()
                u = link.get("url") or ""
                if any(
                    k in text
                    for k in ["annual", "thường niên", "thuong nien", "báo cáo", "report", "pdf"]
                ) or ".pdf" in u.lower():
                    reports.append(
                        {
                            "title": link.get("text") or u,
                            "url": u,
                            "type": link.get("type", "page"),
                        }
                    )
        seen = set()
        unique = []
        for r in reports:
            if r["url"] not in seen:
                seen.add(r["url"])
                unique.append(r)
        return unique[:15]

    def get_exchange_rate(self) -> Dict[str, Any]:
        """Fetch NHNN central exchange rate page and parse numbers."""
        page = self.fetch_page(NHNN_TY_GIA)
        result: Dict[str, Any] = {
            "source": NHNN_TY_GIA,
            "status": page.get("status"),
            "rates": {},
            "raw_snippet": "",
        }
        if page.get("status") != "ok":
            result["error"] = page.get("error")
            return result

        text = page.get("text") or ""
        result["raw_snippet"] = text[:3000]

        # Central rate patterns
        m = re.search(
            r"1\s*Đô\s*la\s*Mỹ\s*=\s*([\d\.,]+)\s*VND",
            text,
            re.IGNORECASE,
        )
        if m:
            result["rates"]["usd_vnd_central"] = m.group(1).replace(".", "").replace(",", "")
        m2 = re.search(r"Tỷ giá trung tâm[^\d]*([\d\.,]+)", text, re.IGNORECASE)
        if m2 and "usd_vnd_central" not in result["rates"]:
            result["rates"]["usd_vnd_central"] = m2.group(1)

        # Table-like: USD buy/sell
        for line in text.split("\n"):
            if re.search(r"\bUSD\b", line, re.I) and re.search(r"\d", line):
                nums = re.findall(r"[\d\.,]+", line)
                if len(nums) >= 2:
                    result["rates"]["usd_buy"] = nums[0]
                    result["rates"]["usd_sell"] = nums[1]
                    break

        result["title"] = page.get("title")
        return result

    def get_latest_nso_report_content(self) -> Dict[str, Any]:
        """Open latest NSO socio-economic report page and extract key indicators from HTML."""
        reports = self.list_nso_latest_reports()
        if not reports:
            return {"status": "error", "error": "No NSO reports listed"}

        # Prefer "Báo cáo tình hình kinh tế"
        preferred = None
        for r in reports:
            t = (r.get("title") or "").lower()
            if "báo cáo tình hình kinh tế" in t or "bao cao tinh hinh kinh te" in t:
                preferred = r
                break
        if not preferred:
            preferred = reports[0]

        page = self.fetch_page(preferred["url"])
        if page.get("status") != "ok":
            return {"status": "error", "error": page.get("error"), "report": preferred}

        text = page.get("text") or ""
        indicators = self._extract_macro_from_text(text)
        return {
            "status": "ok",
            "report": preferred,
            "title": page.get("title"),
            "url": preferred["url"],
            "indicators": indicators,
            "text_preview": text[:4000],
        }

    @staticmethod
    def _extract_macro_from_text(text: str) -> Dict[str, Any]:
        indicators: Dict[str, Any] = {}
        patterns = {
            "gdp_growth_pct": [
                r"GDP.*?tăng\s*([\d,\.]+)\s*%",
                r"tăng\s*([\d,\.]+)\s*%\s*so với cùng kỳ.*?GDP",
                r"GDP.*?([\d,\.]+)\s*%",
            ],
            "cpi_pct": [
                r"CPI.*?tăng\s*([\d,\.]+)\s*%",
                r"CPI.*?([\d,\.]+)\s*%",
                r"lạm phát.*?([\d,\.]+)\s*%",
            ],
            "iip_pct": [
                r"IIP.*?tăng\s*([\d,\.]+)\s*%",
                r"sản xuất công nghiệp.*?tăng\s*([\d,\.]+)\s*%",
            ],
            "export_usd_billion": [
                r"xuất khẩu.*?([\d,\.]+)\s*(tỷ|tỉ)\s*USD",
            ],
            "import_usd_billion": [
                r"nhập khẩu.*?([\d,\.]+)\s*(tỷ|tỉ)\s*USD",
            ],
            "credit_growth_pct": [
                r"tín dụng.*?tăng\s*([\d,\.]+)\s*%",
            ],
        }
        for key, pats in patterns.items():
            for pat in pats:
                m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
                if m:
                    indicators[key] = m.group(1).replace(",", ".")
                    break
        return indicators

    def collect_macro_bundle(self) -> Dict[str, Any]:
        """One-shot: exchange rate + latest NSO report indicators."""
        fx = self.get_exchange_rate()
        nso = self.get_latest_nso_report_content()
        nhnn_list = self.list_nhnn_reports()
        nso_list = self.list_nso_latest_reports()
        return {
            "status": "ok",
            "exchange_rate": fx,
            "nso_latest": nso,
            "nso_report_list": nso_list[:10],
            "nhnn_report_list": nhnn_list[:10],
            "collected_at": datetime.utcnow().isoformat() + "Z",
        }
