"""
Company data for ANY entity operating in Vietnam:
- Listed (ticker) → CafeF / Vietstock / SSI
- Unlisted → search by name / MST, company website, business registration portal
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import CompanyProfile, FinancialStatement

logger = get_logger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}


class CompanyDataTool:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get(self, url: str, timeout: int = 25) -> Optional[requests.Response]:
        try:
            r = self.session.get(url, timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                return r
            logger.warning("http_non_200", url=url[:120], status=r.status_code)
        except Exception as e:
            logger.warning("http_error", url=url[:80], error=str(e))
        return None

    # ------------------------------------------------------------------
    # Listed companies (ticker)
    # ------------------------------------------------------------------
    def fetch_by_ticker(self, ticker: str) -> Dict[str, Any]:
        ticker = ticker.upper().strip()
        out: Dict[str, Any] = {
            "status": "failed",
            "ticker": ticker,
            "company_name": None,
            "profile": None,
            "key_figures": {},
            "financials": [],
            "reports": [],
            "sources": [],
            "error": None,
        }

        # --- CafeF ---
        cafef_url = f"https://s.cafef.vn/hose/{ticker}-cong-ty.chn"
        r = self._get(cafef_url)
        if r:
            out["sources"].append(cafef_url)
            soup = BeautifulSoup(r.text, "lxml")
            title = soup.find("title")
            if title:
                name = re.sub(r"\s*[-|].*$", "", title.get_text(strip=True)).strip()
                if name and ticker not in name.upper():
                    out["company_name"] = name

            body = soup.get_text(" ", strip=True)
            for k, pat in {
                "revenue": r"(?:Doanh thu thuần|Doanh thu)[^\d]{0,40}([\d.,]+)",
                "profit": r"(?:Lợi nhuận sau thuế|LNST|Lợi nhuận)[^\d]{0,40}([\d.,]+)",
                "eps": r"EPS[^\d]{0,20}([\d.,]+)",
                "roe": r"ROE[^\d]{0,15}([\d.,]+)\s*%?",
                "roa": r"ROA[^\d]{0,15}([\d.,]+)\s*%?",
                "pe": r"P/E[^\d]{0,15}([\d.,]+)",
                "pb": r"P/B[^\d]{0,15}([\d.,]+)",
            }.items():
                m = re.search(pat, body, re.I)
                if m:
                    out["key_figures"][k] = m.group(1)

            # PDF / report links
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True)
                if any(x in (href + text).lower() for x in [".pdf", "bctc", "báo cáo", "annual", "financial"]):
                    full = urljoin(cafef_url, href)
                    out["reports"].append({"title": text[:180] or "BCTC", "url": full, "source": "cafef"})

        # --- Vietstock ---
        vs_url = f"https://finance.vietstock.vn/{ticker}/tai-chinh.htm"
        r = self._get(vs_url)
        if r:
            out["sources"].append(vs_url)
            soup = BeautifulSoup(r.text, "lxml")
            if not out["company_name"]:
                t = soup.find("title")
                if t:
                    out["company_name"] = re.sub(r"\s*[-|].*$", "", t.get_text(strip=True)).strip()

            body = soup.get_text(" ", strip=True)
            for k, pat in {
                "revenue": r"(?:Doanh thu|Revenue)[^\d]{0,30}([\d.,]+)",
                "profit": r"(?:Lợi nhuận|Profit|LNST)[^\d]{0,30}([\d.,]+)",
                "eps": r"EPS[^\d]{0,20}([\d.,]+)",
            }.items():
                if k not in out["key_figures"]:
                    m = re.search(pat, body, re.I)
                    if m:
                        out["key_figures"][k] = m.group(1)

            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True)
                if ".pdf" in href.lower() or "bctc" in text.lower():
                    full = urljoin(vs_url, href)
                    out["reports"].append({"title": text[:180], "url": full, "source": "vietstock"})

        # --- SSI fallback ---
        ssi = self._get(f"https://finance.ssi.com.vn/StockInfo?code={ticker}")
        if ssi:
            out["sources"].append(f"https://finance.ssi.com.vn/StockInfo?code={ticker}")
            soup = BeautifulSoup(ssi.text, "lxml")
            if not out["company_name"]:
                t = soup.find("title")
                if t:
                    out["company_name"] = t.get_text(strip=True)[:150]

        # Dedup reports
        seen = set()
        unique = []
        for rep in sorted(out["reports"], key=lambda x: (0 if ".pdf" in x["url"].lower() else 1)):
            u = rep["url"].split("?")[0]
            if u not in seen:
                seen.add(u)
                unique.append(rep)
        out["reports"] = unique[:15]

        if out["company_name"] or out["key_figures"] or out["reports"]:
            out["status"] = "ok" if (out["key_figures"] or out["reports"]) else "partial"
            out["profile"] = CompanyProfile(
                name=out["company_name"] or ticker,
                ticker=ticker,
                listing_status="listed",
                exchange="HOSE/HNX/UPCOM",
            )
        else:
            out["error"] = f"Không tìm thấy dữ liệu cho mã {ticker}"
            out["status"] = "failed"

        return out

    # ------------------------------------------------------------------
    # Any company (name / MST)
    # ------------------------------------------------------------------
    def search_by_name(self, name: str, tax_code: Optional[str] = None) -> Dict[str, Any]:
        """
        Search for any company operating in Vietnam.
        Sources: CafeF search, Vietstock, general web patterns, business portal hints.
        """
        out: Dict[str, Any] = {
            "status": "failed",
            "query_name": name,
            "tax_code": tax_code,
            "company_name": None,
            "profile": None,
            "key_figures": {},
            "financials": [],
            "reports": [],
            "sources": [],
            "candidates": [],
            "error": None,
        }

        query = name.strip()
        if tax_code:
            query = f"{query} {tax_code}".strip()

        # 1. CafeF company search
        search_url = f"https://s.cafef.vn/tim-kiem.chn?keyword={quote(query)}"
        r = self._get(search_url)
        if r:
            out["sources"].append(search_url)
            soup = BeautifulSoup(r.text, "lxml")
            for a in soup.select("a[href*='-cong-ty'], a[href*='hose'], a[href*='hnx']")[:10]:
                href = a.get("href", "")
                text = a.get_text(strip=True)
                if len(text) > 5:
                    full = urljoin("https://s.cafef.vn/", href)
                    out["candidates"].append({"name": text[:120], "url": full, "source": "cafef"})

        # 2. Vietstock search
        vs_search = f"https://finance.vietstock.vn/search/{quote(query)}"
        r = self._get(vs_search)
        if r:
            out["sources"].append(vs_search)
            soup = BeautifulSoup(r.text, "lxml")
            for a in soup.find_all("a", href=True)[:15]:
                href = a["href"]
                text = a.get_text(strip=True)
                if any(x in href.lower() for x in ["/hose/", "/hnx/", "/upcom/", "tai-chinh"]):
                    full = urljoin("https://finance.vietstock.vn/", href)
                    out["candidates"].append({"name": text[:120], "url": full, "source": "vietstock"})

        # 3. If we found a strong candidate that looks listed → treat as ticker path
        ticker_match = None
        for c in out["candidates"]:
            m = re.search(r"/([A-Z]{3,4})(?:-|/|$)", c["url"], re.I)
            if m:
                ticker_match = m.group(1).upper()
                break

        if ticker_match:
            listed = self.fetch_by_ticker(ticker_match)
            if listed.get("status") in ("ok", "partial"):
                listed["search_origin"] = "name→ticker"
                return listed

        # 4. Build basic profile from best candidate
        if out["candidates"]:
            best = out["candidates"][0]
            out["company_name"] = best["name"]
            out["profile"] = CompanyProfile(
                name=best["name"],
                tax_code=tax_code,
                listing_status="unlisted",
                description=f"Kết quả tìm kiếm cho '{name}'. Dữ liệu chi tiết hạn chế vì công ty có thể chưa niêm yết.",
            )
            out["status"] = "partial"
            out["reports"].append({
                "title": f"Trang thông tin: {best['name']}",
                "url": best["url"],
                "source": best.get("source", "search"),
            })
        else:
            # Minimal profile so analysis can still proceed with LLM knowledge + user query
            out["company_name"] = name
            out["profile"] = CompanyProfile(
                name=name,
                tax_code=tax_code,
                listing_status="unlisted",
                description=(
                    f"Không tìm thấy dữ liệu công khai đầy đủ cho '{name}'. "
                    "Phân tích sẽ dựa trên thông tin vĩ mô, ngành và kiến thức tổng hợp."
                ),
            )
            out["status"] = "partial"
            out["error"] = "Dữ liệu công ty hạn chế – khuyến nghị bổ sung BCTC thủ công nếu có."

        return out

    def resolve_company(
        self,
        name: Optional[str] = None,
        ticker: Optional[str] = None,
        tax_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Unified entry: prefer ticker, else name/MST."""
        if ticker:
            return self.fetch_by_ticker(ticker)
        if name or tax_code:
            return self.search_by_name(name or "", tax_code=tax_code)
        return {
            "status": "failed",
            "error": "Cần cung cấp tên công ty, mã CK hoặc MST",
            "profile": None,
            "key_figures": {},
            "reports": [],
            "sources": [],
        }
