"""
Official sources collector for Vietnamese macro + company financial reports.

- NHNN / SBV: exchange rate, monetary reports
- NSO / GSO: socio-economic reports, GDP, CPI, trade
- Company: financial reports by stock ticker (CafeF, Vietstock)
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}


class OfficialSourceTool:
    """Reliable scraper for SBV, NSO and company financial reports."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get(self, url: str, timeout: int = 20) -> Optional[requests.Response]:
        try:
            r = self.session.get(url, timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                return r
            logger.warning("http_non_200", url=url, status=r.status_code)
        except Exception as e:
            logger.warning("http_error", url=url, error=str(e))
        return None

    def download_file(self, url: str, subdir: str = "other") -> Dict[str, Any]:
        result: Dict[str, Any] = {"url": url, "status": "failed"}
        try:
            r = self.session.get(url, timeout=45, stream=True)
            if r.status_code != 200:
                result["error"] = f"HTTP {r.status_code}"
                return result
            parsed = urlparse(url)
            name = Path(parsed.path).name or f"file_{int(time.time())}.bin"
            name = re.sub(r"[^\w.\-]", "_", name)[:120]
            folder = self.settings.raw_dir / subdir
            folder.mkdir(parents=True, exist_ok=True)
            local = folder / name
            with open(local, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
            result.update({
                "status": "ok",
                "local_path": str(local),
                "file_name": name,
                "size_bytes": local.stat().st_size,
            })
            logger.info("download_ok", path=str(local), size=result["size_bytes"])
        except Exception as e:
            result["error"] = str(e)
            logger.exception("download_failed", url=url)
        return result

    def fetch_exchange_rate(self) -> Dict[str, Any]:
        urls = [
            "https://www.sbv.gov.vn/webcenter/portal/vi/menu/rm/tg",
            "https://sbv.gov.vn",
            "https://www.sbv.gov.vn",
        ]
        out: Dict[str, Any] = {"status": "failed", "rates": {}, "source": None}
        for url in urls:
            r = self._get(url)
            if not r:
                continue
            text = r.text
            patterns = [
                r"USD[^\d]{0,20}(\d{1,3}[.,]\d{3})",
                r"Tỷ giá trung tâm[^\d]{0,30}(\d{1,3}[.,]\d{3})",
                r"(\d{2}\s?[.,]\s?\d{3})\s*(?:VND)?\s*/?\s*USD",
            ]
            for pat in patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    raw = m.group(1) if m.lastindex else m.group(0)
                    digits = re.sub(r"[^\d]", "", raw)
                    if len(digits) >= 4:
                        rate = int(digits)
                        if 15000 < rate < 40000:
                            out["rates"]["usd_vnd_central"] = str(rate)
                            out["status"] = "ok"
                            out["source"] = url
                            return out
            soup = BeautifulSoup(text, "lxml")
            body = soup.get_text(" ", strip=True)
            m2 = re.search(r"(?:USD|Đô\s*la)[^\d]{0,40}(\d{2}[.,]\d{3})", body, re.I)
            if m2:
                digits = re.sub(r"[^\d]", "", m2.group(1))
                rate = int(digits)
                if 15000 < rate < 40000:
                    out["rates"]["usd_vnd_central"] = str(rate)
                    out["status"] = "ok"
                    out["source"] = url
                    return out
        out["notes"] = "Không scrape được tỷ giá realtime"
        return out

    def fetch_nso_latest(self) -> Dict[str, Any]:
        list_urls = [
            "https://www.nso.gov.vn/thong-tin-thong-ke/bao-cao-tinh-hinh-kinh-te-xa-hoi/",
            "https://www.gso.gov.vn/bao-cao-tinh-hinh-kinh-te-xa-hoi/",
            "https://www.nso.gov.vn/",
        ]
        out: Dict[str, Any] = {
            "status": "failed",
            "url": None,
            "title": None,
            "indicators": {},
            "text_preview": "",
            "report_links": [],
        }
        for list_url in list_urls:
            r = self._get(list_url)
            if not r:
                continue
            soup = BeautifulSoup(r.text, "lxml")
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(" ", strip=True)
                low = (href + " " + text).lower()
                if any(k in low for k in [
                    "kinh-te-xa-hoi", "kinh tế - xã hội",
                    "bao-cao-tinh-hinh", "socio-economic",
                ]):
                    full = urljoin(list_url, href)
                    links.append({"title": text[:200], "url": full})
            if links:
                out["report_links"] = links[:10]
                for link in links[:5]:
                    detail = self._get(link["url"])
                    if not detail:
                        continue
                    text = BeautifulSoup(detail.text, "lxml").get_text(" ", strip=True)
                    inds = self._parse_macro_indicators(text)
                    if inds:
                        out["status"] = "ok"
                        out["url"] = link["url"]
                        out["title"] = link["title"]
                        out["indicators"] = inds
                        out["text_preview"] = text[:3000]
                        return out
                out["status"] = "partial"
                out["url"] = links[0]["url"]
                out["title"] = links[0]["title"]
                return out
        return out

    def _parse_macro_indicators(self, text: str) -> Dict[str, str]:
        inds: Dict[str, str] = {}
        patterns = {
            "gdp_growth_pct": [
                r"GDP[^\d]{0,40}(?:tăng|đạt|ước)[^\d]{0,20}(\d+[.,]\d+)\s*%",
                r"tăng trưởng[^\d]{0,30}(\d+[.,]\d+)\s*%",
            ],
            "cpi_pct": [
                r"CPI[^\d]{0,40}(?:tăng|giảm)?[^\d]{0,15}(\d+[.,]\d+)\s*%",
                r"chỉ số giá tiêu dùng[^\d]{0,40}(\d+[.,]\d+)\s*%",
            ],
            "credit_growth_pct": [
                r"tín dụng[^\d]{0,40}(?:tăng)[^\d]{0,15}(\d+[.,]\d+)\s*%",
            ],
            "exports": [r"xuất khẩu[^\d]{0,40}(\d+[.,]?\d*)\s*(tỷ|tỉ)"],
            "imports": [r"nhập khẩu[^\d]{0,40}(\d+[.,]?\d*)\s*(tỷ|tỉ)"],
            "trade_balance": [r"(?:xuất siêu|nhập siêu)[^\d]{0,30}(\d+[.,]?\d*)\s*(tỷ|tỉ)"],
        }
        for key, pats in patterns.items():
            for pat in pats:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    inds[key] = m.group(1).replace(",", ".")
                    break
        return inds

    def list_nhnn_reports(self) -> List[Dict[str, str]]:
        urls = [
            "https://www.sbv.gov.vn/webcenter/portal/vi/menu/rm/bc",
            "https://sbv.gov.vn",
        ]
        reports: List[Dict[str, str]] = []
        seen = set()
        for base in urls:
            r = self._get(base)
            if not r:
                continue
            soup = BeautifulSoup(r.text, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                title = a.get_text(" ", strip=True)
                low = (href + " " + title).lower()
                if any(k in low for k in [
                    "annual", "báo cáo thường niên", "bao-cao",
                    "report", ".pdf", "monetary", "tiền tệ",
                ]):
                    full = urljoin(base, href)
                    if full not in seen and len(title) > 5:
                        seen.add(full)
                        reports.append({"title": title[:250], "url": full})
        return reports[:20]

    def list_nso_reports(self) -> List[Dict[str, str]]:
        nso = self.fetch_nso_latest()
        return nso.get("report_links") or []

    def fetch_company_reports(self, ticker: str) -> Dict[str, Any]:
        ticker = (ticker or "").strip().upper()
        out: Dict[str, Any] = {
            "status": "failed",
            "ticker": ticker,
            "company_name": None,
            "reports": [],
            "key_figures": {},
            "sources": [],
        }
        if not ticker or not re.match(r"^[A-Z0-9]{3,10}$", ticker):
            out["error"] = "Mã chứng khoán không hợp lệ (3–10 ký tự chữ/số)"
            return out

        cafef_url = f"https://s.cafef.vn/hose/{ticker}-bao-cao-tai-chinh.chn"
        r = self._get(cafef_url)
        if r:
            out["sources"].append(cafef_url)
            soup = BeautifulSoup(r.text, "lxml")
            title_tag = soup.find("title")
            if title_tag:
                out["company_name"] = title_tag.get_text(strip=True)[:120]
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(" ", strip=True)
                low = (href + " " + text).lower()
                if any(k in low for k in [
                    "bao-cao", "bctc", "financial", ".pdf",
                    "quy", "năm", "audit", "kiem-toan",
                ]):
                    full = urljoin(cafef_url, href)
                    out["reports"].append({
                        "title": text[:200] or full,
                        "url": full,
                        "source": "cafef",
                    })
            body = soup.get_text(" ", strip=True)
            for k, pat in {
                "revenue": r"(?:Doanh thu|Revenue)[^\d]{0,30}([\d.,]+)",
                "profit": r"(?:Lợi nhuận|Profit|LNST)[^\d]{0,30}([\d.,]+)",
                "eps": r"EPS[^\d]{0,20}([\d.,]+)",
            }.items():
                m = re.search(pat, body, re.I)
                if m:
                    out["key_figures"][k] = m.group(1)

        vs_url = f"https://finance.vietstock.vn/{ticker}/tai-chinh.htm"
        r2 = self._get(vs_url)
        if r2:
            out["sources"].append(vs_url)
            soup2 = BeautifulSoup(r2.text, "lxml")
            if not out["company_name"]:
                t2 = soup2.find("title")
                if t2:
                    out["company_name"] = t2.get_text(strip=True)[:120]
            for a in soup2.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(" ", strip=True)
                low = (href + " " + text).lower()
                if any(k in low for k in [".pdf", "bctc", "bao-cao", "financial"]):
                    full = urljoin(vs_url, href)
                    out["reports"].append({
                        "title": text[:200] or full,
                        "url": full,
                        "source": "vietstock",
                    })

        seen = set()
        unique = []
        for rep in out["reports"]:
            if rep["url"] not in seen:
                seen.add(rep["url"])
                unique.append(rep)
        out["reports"] = unique[:15]

        if out["reports"] or out["key_figures"] or out["company_name"]:
            out["status"] = "ok" if (out["reports"] or out["key_figures"]) else "partial"
        else:
            out["error"] = f"Không tìm thấy báo cáo cho mã {ticker}"
        return out

    def collect_macro_bundle(self) -> Dict[str, Any]:
        logger.info("collect_macro_bundle_start")
        fx = self.fetch_exchange_rate()
        nso = self.fetch_nso_latest()
        nhnn_list = self.list_nhnn_reports()
        nso_list = self.list_nso_reports()
        bundle = {
            "exchange_rate": fx,
            "nso_latest": nso,
            "nhnn_report_list": nhnn_list,
            "nso_report_list": nso_list,
            "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        logger.info(
            "collect_macro_bundle_done",
            fx=fx.get("status"),
            nso=nso.get("status"),
            nhnn_count=len(nhnn_list),
            nso_count=len(nso_list),
        )
        return bundle
