"""
Tools for fetching official Vietnamese government reports.
Hard-coded trusted entry points to avoid hallucination.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Trusted entry points (updated periodically)
NHNN_ANNUAL_REPORTS = "https://sbv.gov.vn/en/w/annual-report-2023"  # example, agent will search newer
NHNN_BASE = "https://sbv.gov.vn"
NSO_BASE = "https://www.nso.gov.vn"
NSO_REPORTS_SECTION = "https://www.nso.gov.vn/bai-top/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; VietnamMacroAgent/1.0; +https://github.com/)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}


class OfficialSourceTool:
    """Safe fetcher for NHNN + NSO official pages and documents."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = httpx.Client(
            headers=HEADERS,
            timeout=30.0,
            follow_redirects=True,
        )

    def close(self) -> None:
        self.client.close()

    def fetch_page(self, url: str) -> Dict[str, Any]:
        """Fetch a page and return title + text + links to PDF/Excel."""
        logger.info("fetch_page", url=url)
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            title = soup.title.string.strip() if soup.title else ""
            # Remove scripts/styles
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()

            text = soup.get_text(separator="\n", strip=True)
            text = re.sub(r"\n{3,}", "\n\n", text)

            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                full = urljoin(url, href)
                text_a = a.get_text(strip=True)
                lower = full.lower()
                if any(ext in lower for ext in [".pdf", ".xlsx", ".xls", ".csv", ".doc"]):
                    links.append({"url": full, "text": text_a, "type": Path(full).suffix.lower()})
                elif "bao-cao" in lower or "report" in lower or "nien-giam" in lower:
                    links.append({"url": full, "text": text_a, "type": "page"})

            return {
                "url": url,
                "title": title,
                "text": text[:15000],  # limit for LLM context
                "links": links[:40],
                "status": "ok",
            }
        except Exception as e:
            logger.error("fetch_page_failed", url=url, error=str(e))
            return {"url": url, "status": "error", "error": str(e)}

    def download_file(self, url: str, subdir: str = "other") -> Dict[str, Any]:
        """Download PDF / Excel to data/raw/{subdir}/."""
        logger.info("download_file", url=url, subdir=subdir)
        try:
            resp = self.client.get(url)
            resp.raise_for_status()

            # Guess filename
            cd = resp.headers.get("content-disposition", "")
            filename = None
            if "filename=" in cd:
                filename = re.findall(r'filename="?([^";]+)"?', cd)
                filename = filename[0] if filename else None
            if not filename:
                filename = Path(url).name or f"file_{datetime.now():%Y%m%d_%H%M%S}"
            filename = re.sub(r"[^\w\.\-]", "_", filename)[:120]

            dest_dir = self.settings.raw_dir / subdir
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / filename

            dest.write_bytes(resp.content)
            size = dest.stat().st_size

            logger.info("download_success", path=str(dest), size=size)
            return {
                "status": "ok",
                "local_path": str(dest),
                "url": url,
                "size_bytes": size,
                "filename": filename,
            }
        except Exception as e:
            logger.error("download_failed", url=url, error=str(e))
            return {"status": "error", "url": url, "error": str(e)}

    def list_nso_latest_reports(self) -> List[Dict[str, str]]:
        """Heuristic list of recent NSO socio-economic reports."""
        page = self.fetch_page(NSO_REPORTS_SECTION)
        reports = []
        if page.get("status") != "ok":
            return reports

        for link in page.get("links", []):
            text = link.get("text", "").lower()
            if any(k in text for k in ["kinh tế", "kinh te", "xã hội", "xa hoi", "gdp", "báo cáo"]):
                reports.append({
                    "title": link.get("text"),
                    "url": link.get("url"),
                    "type": link.get("type"),
                })
        return reports[:15]

    def list_nhnn_reports(self) -> List[Dict[str, str]]:
        """Heuristic list from NHNN annual reports / news."""
        # Start from known annual report page and homepage sections
        candidates = [
            "https://sbv.gov.vn/en/w/annual-report-2023",
            "https://sbv.gov.vn/vi/w/b%C3%A1o-c%C3%A1o-th%C6%B0%E1%BB%9Dng-ni%C3%AAn",
            "https://sbv.gov.vn",
        ]
        reports = []
        for url in candidates:
            page = self.fetch_page(url)
            if page.get("status") != "ok":
                continue
            for link in page.get("links", []):
                text = (link.get("text") or "").lower()
                if any(k in text for k in ["annual", "thường niên", "thuong nien", "báo cáo", "report"]):
                    reports.append({
                        "title": link.get("text"),
                        "url": link.get("url"),
                        "type": link.get("type"),
                    })
        # Dedupe by url
        seen = set()
        unique = []
        for r in reports:
            if r["url"] not in seen:
                seen.add(r["url"])
                unique.append(r)
        return unique[:15]
