"""Official macro data: NHNN (SBV) + NSO (GSO)."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import MacroSnapshot

logger = get_logger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}


class MacroDataTool:
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

    def fetch_exchange_rate(self) -> Dict[str, Any]:
        """Tỷ giá trung tâm NHNN."""
        out: Dict[str, Any] = {"status": "failed", "rates": {}, "sources": []}
        urls = [
            "https://www.sbv.gov.vn/webcenter/portal/vi/menu/rm/tg?_afrLoop=0",
            "https://portal.sbv.gov.vn/webcenter/portal/m/menu/trangchu/tg",
        ]
        for url in urls:
            r = self._get(url)
            if not r:
                continue
            out["sources"].append(url)
            soup = BeautifulSoup(r.text, "lxml")
            text = soup.get_text(" ", strip=True)
            # Common patterns
            m = re.search(
                r"(?:Tỷ giá trung tâm|Central rate|USD/VND)[^\d]{0,40}([\d.,]+)",
                text,
                re.I,
            )
            if m:
                val = m.group(1).replace(".", "").replace(",", ".")
                try:
                    out["rates"]["usd_vnd_central"] = float(val)
                    out["status"] = "ok"
                    break
                except ValueError:
                    pass
            # Table fallback
            for td in soup.find_all(["td", "span", "div"]):
                t = td.get_text(strip=True)
                if re.match(r"^[\d.,]{5,}$", t) and "USD" in (td.parent.get_text() if td.parent else ""):
                    try:
                        out["rates"]["usd_vnd_central"] = float(t.replace(".", "").replace(",", "."))
                        out["status"] = "ok"
                        break
                    except ValueError:
                        continue
            if out["status"] == "ok":
                break
        return out

    def fetch_nso_latest(self) -> Dict[str, Any]:
        """Báo cáo tình hình KT-XH NSO."""
        out: Dict[str, Any] = {
            "status": "failed",
            "indicators": {},
            "report_links": [],
            "sources": [],
        }
        base = "https://www.nso.gov.vn"
        list_url = f"{base}/vi/thong-tin-thong-ke/thong-tin-kinh-te-xa-hoi/"
        r = self._get(list_url)
        if not r:
            # Alternate
            r = self._get(f"{base}/default.aspx")
        if not r:
            return out

        out["sources"].append(list_url)
        soup = BeautifulSoup(r.text, "lxml")
        text = soup.get_text(" ", strip=True)

        patterns = {
            "gdp_growth": r"(?:GDP|Tăng trưởng\s*(?:GDP|kinh tế))[^\d]{0,30}([\d.,]+)\s*%",
            "cpi_yoy": r"(?:CPI|Lạm phát)[^\d]{0,25}([\d.,]+)\s*%",
            "credit_growth": r"(?:Tín dụng|Credit growth)[^\d]{0,25}([\d.,]+)\s*%",
            "industrial_production": r"(?:Sản xuất công nghiệp|IIP)[^\d]{0,25}([\d.,]+)\s*%",
            "retail_sales_growth": r"(?:Bán lẻ|Retail)[^\d]{0,25}([\d.,]+)\s*%",
            "export_growth": r"(?:Xuất khẩu|Export)[^\d]{0,25}([\d.,]+)\s*%",
            "import_growth": r"(?:Nhập khẩu|Import)[^\d]{0,25}([\d.,]+)\s*%",
            "fdi_disbursed": r"(?:FDI thực hiện|Giải ngân FDI)[^\d]{0,30}([\d.,]+)",
        }
        for key, pat in patterns.items():
            m = re.search(pat, text, re.I)
            if m:
                try:
                    out["indicators"][key] = float(m.group(1).replace(",", "."))
                except ValueError:
                    out["indicators"][key] = m.group(1)

        # Collect report links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            title = a.get_text(strip=True)
            if any(k in title.lower() for k in ["báo cáo", "tình hình", "kinh tế", "xã hội", "tháng", "quý"]):
                full = urljoin(base, href)
                if full not in [x["url"] for x in out["report_links"]]:
                    out["report_links"].append({"title": title[:180], "url": full})

        out["report_links"] = out["report_links"][:15]
        if out["indicators"] or out["report_links"]:
            out["status"] = "ok" if out["indicators"] else "partial"
        return out

    def list_nhnn_reports(self) -> List[Dict[str, str]]:
        reports = []
        urls = [
            "https://www.sbv.gov.vn/webcenter/portal/vi/menu/rm/bc",
            "https://www.sbv.gov.vn/",
        ]
        for url in urls:
            r = self._get(url)
            if not r:
                continue
            soup = BeautifulSoup(r.text, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                title = a.get_text(strip=True)
                if any(k in (title + href).lower() for k in ["báo cáo", "report", "thống kê", "annual", ".pdf"]):
                    full = urljoin(url, href)
                    reports.append({"title": title[:200], "url": full, "source": "nhnn"})
            if reports:
                break
        # Dedup
        seen = set()
        unique = []
        for x in reports:
            if x["url"] not in seen:
                seen.add(x["url"])
                unique.append(x)
        return unique[:20]

    def collect_snapshot(self) -> MacroSnapshot:
        """Build MacroSnapshot for report."""
        fx = self.fetch_exchange_rate()
        nso = self.fetch_nso_latest()
        nhnn = self.list_nhnn_reports()

        ind = nso.get("indicators") or {}
        rates = fx.get("rates") or {}

        sources = list(set(
            (fx.get("sources") or []) +
            (nso.get("sources") or []) +
            [r["url"] for r in nhnn[:5]]
        ))

        notes = []
        if fx.get("status") != "ok":
            notes.append("Tỷ giá NHNN chưa lấy được trực tiếp trong lần chạy này.")
        if nso.get("status") not in ("ok", "partial"):
            notes.append("Chỉ số NSO hạn chế – cần kiểm tra nguồn gốc.")

        return MacroSnapshot(
            as_of=time.strftime("%Y-%m-%d"),
            gdp_growth=ind.get("gdp_growth"),
            cpi_yoy=ind.get("cpi_yoy"),
            credit_growth=ind.get("credit_growth"),
            usd_vnd=rates.get("usd_vnd_central"),
            trade_balance=None,
            fdi_disbursed=ind.get("fdi_disbursed"),
            notes=notes,
            sources=sources[:10],
        )
