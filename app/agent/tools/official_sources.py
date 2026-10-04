"""
Official sources: SBV (tỷ giá + báo cáo), NSO (vĩ mô), Company BCTC by ticker.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse, quote

import requests
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}


class OfficialSourceTool:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get(self, url: str, timeout: int = 25) -> Optional[requests.Response]:
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
            r = self.session.get(url, timeout=60, stream=True)
            if r.status_code != 200:
                result["error"] = f"HTTP {r.status_code}"
                return result
            parsed = urlparse(url)
            name = Path(parsed.path).name or f"file_{int(time.time())}.bin"
            name = re.sub(r"[^\w.\-]", "_", name)[:120]
            if not name.lower().endswith((".pdf", ".xlsx", ".xls", ".doc", ".docx", ".csv")):
                ctype = r.headers.get("Content-Type", "")
                if "pdf" in ctype:
                    name += ".pdf"
                elif "sheet" in ctype or "excel" in ctype:
                    name += ".xlsx"
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

    # ------------------------------------------------------------------
    # SBV exchange rate — multiple endpoints
    # ------------------------------------------------------------------
    def fetch_exchange_rate(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"status": "failed", "rates": {}, "source": None}

        # 1) Try SBV public pages
        pages = [
            "https://www.sbv.gov.vn/webcenter/portal/vi/menu/rm/tg",
            "https://www.sbv.gov.vn/webcenter/portal/en/home/sbv/er",
            "https://sbv.gov.vn",
        ]
        for url in pages:
            r = self._get(url)
            if not r:
                continue
            text = BeautifulSoup(r.text, "lxml").get_text(" ", strip=True)
            for pat in [
                r"(?:tỷ giá trung tâm|central rate|USD)[^\d]{0,40}(\d{2}[.,]\d{3})",
                r"(\d{2}[.,]\d{3})\s*(?:VND)?\s*/?\s*USD",
                r"USD[^\d]{0,15}(\d{2}[.,]\d{3})",
            ]:
                m = re.search(pat, text, re.I)
                if m:
                    digits = re.sub(r"[^\d]", "", m.group(1))
                    rate = int(digits)
                    if 18000 < rate < 35000:
                        out["rates"]["usd_vnd_central"] = str(rate)
                        out["status"] = "ok"
                        out["source"] = url
                        return out

        # 2) Fallback: Vietcombank public rate (widely used reference)
        vcb = self._get("https://portal.vietcombank.com.vn/UserControls/TVPortal.TyGia/pXML.aspx")
        if vcb and vcb.text:
            # XML format from VCB
            m = re.search(r'CurrencyCode="USD"[^>]*Transfer="([\d,\.]+)"', vcb.text)
            if not m:
                m = re.search(r'CurrencyCode="USD"[^>]*Sell="([\d,\.]+)"', vcb.text)
            if m:
                digits = re.sub(r"[^\d]", "", m.group(1).split(".")[0])
                if digits:
                    rate = int(digits)
                    if 18000 < rate < 35000:
                        out["rates"]["usd_vnd_central"] = str(rate)
                        out["rates"]["note"] = "Vietcombank transfer/sell (tham chiếu)"
                        out["status"] = "ok"
                        out["source"] = "https://portal.vietcombank.com.vn"
                        return out

        # 3) Fallback: cafef / other public
        r = self._get("https://s.cafef.vn/ty-gia-ngoai-te.chn")
        if r:
            text = BeautifulSoup(r.text, "lxml").get_text(" ", strip=True)
            m = re.search(r"USD[^\d]{0,20}(\d{2}[.,]\d{3})", text)
            if m:
                digits = re.sub(r"[^\d]", "", m.group(1))
                rate = int(digits)
                if 18000 < rate < 35000:
                    out["rates"]["usd_vnd_central"] = str(rate)
                    out["rates"]["note"] = "CafeF (tham chiếu)"
                    out["status"] = "ok"
                    out["source"] = "https://s.cafef.vn/ty-gia-ngoai-te.chn"
                    return out

        out["notes"] = "Không lấy được tỷ giá từ SBV/VCB/CafeF"
        return out

    # ------------------------------------------------------------------
    # NSO
    # ------------------------------------------------------------------
    def fetch_nso_latest(self) -> Dict[str, Any]:
        list_urls = [
            "https://www.nso.gov.vn/thong-tin-thong-ke/bao-cao-tinh-hinh-kinh-te-xa-hoi/",
            "https://www.nso.gov.vn/",
            "https://www.gso.gov.vn/bao-cao-tinh-hinh-kinh-te-xa-hoi/",
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
                    "kinh-te-xa-hoi", "kinh tế - xã hội", "kinh tế xã hội",
                    "bao-cao-tinh-hinh", "socio-economic", "quý", "tháng",
                ]):
                    full = urljoin(list_url, href)
                    if "nso.gov.vn" in full or "gso.gov.vn" in full:
                        links.append({"title": text[:200], "url": full})
            # dedupe
            seen = set()
            uniq = []
            for L in links:
                if L["url"] not in seen:
                    seen.add(L["url"])
                    uniq.append(L)
            if uniq:
                out["report_links"] = uniq[:12]
                for link in uniq[:6]:
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
                        out["text_preview"] = text[:3500]
                        return out
                out["status"] = "partial"
                out["url"] = uniq[0]["url"]
                out["title"] = uniq[0]["title"]
                return out
        return out

    def _parse_macro_indicators(self, text: str) -> Dict[str, str]:
        inds: Dict[str, str] = {}
        patterns = {
            "gdp_growth_pct": [
                r"GDP[^\d]{0,50}(?:tăng|đạt|ước)[^\d]{0,25}(\d+[.,]\d+)\s*%",
                r"tăng trưởng(?:\s+GDP)?[^\d]{0,30}(\d+[.,]\d+)\s*%",
            ],
            "cpi_pct": [
                r"CPI[^\d]{0,40}(?:tăng|giảm)?[^\d]{0,20}(\d+[.,]\d+)\s*%",
                r"chỉ số giá tiêu dùng[^\d]{0,40}(\d+[.,]\d+)\s*%",
            ],
            "credit_growth_pct": [
                r"(?:dư nợ\s+)?tín dụng[^\d]{0,40}(?:tăng)[^\d]{0,20}(\d+[.,]\d+)\s*%",
            ],
            "exports": [r"xuất khẩu[^\d]{0,40}(\d+[.,]?\d*)\s*%?"],
            "imports": [r"nhập khẩu[^\d]{0,40}(\d+[.,]?\d*)\s*%?"],
            "trade_balance": [r"(?:xuất siêu|nhập siêu)[^\d]{0,30}(\d+[.,]?\d*)"],
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
            "https://www.sbv.gov.vn/webcenter/portal/vi/menu/trang_chu",
            "https://sbv.gov.vn/vi/danh-muc-bao-cao-dinh-ky",
            "https://www.sbv.gov.vn",
        ]
        reports: List[Dict[str, str]] = []
        seen = set()
        keywords = [
            "thường niên", "annual report", "báo cáo thường niên",
            "bao-cao-thuong-nien", "báo cáo năm", "monetary",
            "chính sách tiền tệ", "báo cáo định kỳ", ".pdf",
        ]
        for base in urls:
            r = self._get(base)
            if not r:
                continue
            soup = BeautifulSoup(r.text, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                title = a.get_text(" ", strip=True)
                low = (href + " " + title).lower()
                if any(k in low for k in keywords) and len(title) > 8:
                    full = urljoin(base, href)
                    if full not in seen:
                        seen.add(full)
                        reports.append({"title": title[:250], "url": full})
        return reports[:25]

    def list_nso_reports(self) -> List[Dict[str, str]]:
        return (self.fetch_nso_latest() or {}).get("report_links") or []

    # ------------------------------------------------------------------
    # Company BCTC — STRICT filter, correct URLs
    # ------------------------------------------------------------------
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
            out["error"] = "Mã chứng khoán không hợp lệ"
            return out

        # Keywords that indicate REAL financial reports (not news)
        FIN_KEYWORDS = [
            "bctc", "báo cáo tài chính", "bao-cao-tai-chinh",
            "financial statement", "financial report",
            "báo cáo thường niên", "annual report", "bao-cao-thuong-nien",
            "báo cáo quản trị", "quý 1", "quý 2", "quý 3", "quý 4",
            "q1", "q2", "q3", "q4", "kiểm toán", "audited",
            "hợp nhất", "riêng", "bán niên", "six-month",
        ]
        # Keywords that are NEWS — exclude
        NEWS_EXCLUDE = [
            "tin tức", "tin-tuc", "gọi điện", "chuyển khoản",
            "chân dung", "chủ tịch", "nhân viên", "dòng tiền những tháng",
            "xu hướng", "bamboo", "flc", "đột quỵ", "công an",
        ]

        def is_fin_report(title: str, href: str) -> bool:
            low = (title + " " + href).lower()
            if any(x in low for x in NEWS_EXCLUDE):
                return False
            # Must have fin keyword OR be a direct file
            if any(x in low for x in FIN_KEYWORDS):
                return True
            if any(low.endswith(ext) or ext in low for ext in [".pdf", ".xlsx", ".xls", ".doc"]):
                # file link but not news domain noise
                if "tin-tuc" in low or "/tin/" in low:
                    return False
                return True
            return False

        # --- CafeF dedicated BCTC pages ---
        cafef_urls = [
            f"https://s.cafef.vn/hose/{ticker}-bao-cao-tai-chinh.chn",
            f"https://s.cafef.vn/hose/{ticker}-bao-cao-tai-chinh-nam.chn",
            f"https://s.cafef.vn/{ticker}-bao-cao-tai-chinh.chn",
            f"https://cafef.vn/{ticker.lower()}-bao-cao-tai-chinh.chn",
        ]
        for cafef_url in cafef_urls:
            r = self._get(cafef_url)
            if not r:
                continue
            out["sources"].append(cafef_url)
            soup = BeautifulSoup(r.text, "lxml")
            # company name from title
            t = soup.find("title")
            if t and not out["company_name"]:
                name = t.get_text(strip=True)
                # clean "VNM: Công ty..." style
                out["company_name"] = name[:150]

            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(" ", strip=True)
                if not is_fin_report(text, href):
                    continue
                full = urljoin(cafef_url, href)
                # skip pure navigation
                if full.rstrip("/").endswith((".chn", ".htm", ".html")) and ".pdf" not in full.lower():
                    # keep only if title strongly indicates BCTC
                    if not any(k in text.lower() for k in ["bctc", "báo cáo tài chính", "thường niên", "quý", "q1", "q2", "q3", "q4"]):
                        continue
                out["reports"].append({
                    "title": text[:200] or full,
                    "url": full,
                    "source": "cafef",
                })

            # key figures from page
            body = soup.get_text(" ", strip=True)
            for k, pat in {
                "revenue": r"(?:Doanh thu thuần|Doanh thu|Net revenue)[^\d]{0,40}([\d.,]+)",
                "profit": r"(?:LNST|Lợi nhuận sau thuế|Net profit)[^\d]{0,40}([\d.,]+)",
                "eps": r"(?:EPS|Thu nhập trên cổ phiếu)[^\d]{0,25}([\d.,]+)",
                "roe": r"ROE[^\d]{0,20}([\d.,]+)\s*%?",
            }.items():
                m = re.search(pat, body, re.I)
                if m and k not in out["key_figures"]:
                    out["key_figures"][k] = m.group(1)

        # --- Vietstock document pages (more reliable for actual report files) ---
        vs_pages = [
            f"https://finance.vietstock.vn/{ticker}/tai-chinh.htm",
            f"https://finance.vietstock.vn/{ticker}/bao-cao-tai-chinh.htm",
            f"https://finance.vietstock.vn/tai-lieu/bao-cao-tai-chinh.htm?code={ticker}",
            f"https://finance.vietstock.vn/{ticker}/document.htm",
        ]
        for vs_url in vs_pages:
            r = self._get(vs_url)
            if not r:
                continue
            if vs_url not in out["sources"]:
                out["sources"].append(vs_url)
            soup = BeautifulSoup(r.text, "lxml")
            if not out["company_name"]:
                t = soup.find("title")
                if t:
                    out["company_name"] = t.get_text(strip=True)[:150]

            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(" ", strip=True)
                if not is_fin_report(text, href):
                    continue
                full = urljoin(vs_url, href)
                # Prefer actual file links
                out["reports"].append({
                    "title": text[:200] or full,
                    "url": full,
                    "source": "vietstock",
                })

            body = soup.get_text(" ", strip=True)
            for k, pat in {
                "revenue": r"(?:Doanh thu|Revenue)[^\d]{0,30}([\d.,]+)",
                "profit": r"(?:Lợi nhuận|Profit|LNST)[^\d]{0,30}([\d.,]+)",
                "eps": r"EPS[^\d]{0,20}([\d.,]+)",
            }.items():
                m = re.search(pat, body, re.I)
                if m and k not in out["key_figures"]:
                    out["key_figures"][k] = m.group(1)

        # --- SSI / HOSE fallback: search page ---
        ssi = self._get(f"https://finance.ssi.com.vn/StockInfo?code={ticker}")
        if ssi:
            out["sources"].append(f"https://finance.ssi.com.vn/StockInfo?code={ticker}")
            soup = BeautifulSoup(ssi.text, "lxml")
            if not out["company_name"]:
                t = soup.find("title")
                if t:
                    out["company_name"] = t.get_text(strip=True)[:150]

        # Deduplicate by URL, prefer PDF links first
        seen = set()
        unique = []
        for rep in sorted(
            out["reports"],
            key=lambda x: (0 if ".pdf" in x["url"].lower() else 1, x["title"]),
        ):
            u = rep["url"].split("?")[0]
            if u not in seen:
                seen.add(u)
                unique.append(rep)
        out["reports"] = unique[:12]

        if out["reports"] or out["key_figures"] or out["company_name"]:
            out["status"] = "ok" if (out["reports"] or out["key_figures"]) else "partial"
        else:
            out["error"] = f"Không tìm thấy BCTC cho mã {ticker}"
            out["status"] = "failed"

        return out

    def collect_macro_bundle(self) -> Dict[str, Any]:
        logger.info("collect_macro_bundle_start")
        fx = self.fetch_exchange_rate()
        nso = self.fetch_nso_latest()
        nhnn_list = self.list_nhnn_reports()
        nso_list = nso.get("report_links") or []
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
        )
        return bundle
