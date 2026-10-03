"""
Professional PDF extractor for Vietnamese official reports.
Uses pdfplumber + PyMuPDF with fallback strategies.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pdfplumber
import fitz  # PyMuPDF
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)


class PDFExtractor:
    """Extract text and tables from PDF files (NHNN, NSO reports)."""

    def __init__(self, max_pages: int = 80) -> None:
        self.max_pages = max_pages

    def extract(self, file_path: str | Path) -> Dict[str, Any]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")

        logger.info("pdf_extract_start", path=str(path))

        result: Dict[str, Any] = {
            "file": str(path),
            "text": "",
            "tables": [],
            "metadata": {},
            "pages_processed": 0,
        }

        # Metadata + text via PyMuPDF (fast)
        try:
            doc = fitz.open(path)
            result["metadata"] = {
                "page_count": doc.page_count,
                "title": doc.metadata.get("title") or path.stem,
                "author": doc.metadata.get("author"),
            }
            texts = []
            for i, page in enumerate(doc):
                if i >= self.max_pages:
                    break
                texts.append(page.get_text("text"))
            result["text"] = "\n\n".join(texts)
            result["pages_processed"] = min(doc.page_count, self.max_pages)
            doc.close()
        except Exception as e:
            logger.warning("pymupdf_failed", error=str(e))

        # Tables via pdfplumber (more accurate for structured tables)
        try:
            tables = self._extract_tables_pdfplumber(path)
            result["tables"] = tables
        except Exception as e:
            logger.warning("pdfplumber_tables_failed", error=str(e))
            # Fallback: try simple table detection with PyMuPDF if needed
            pass

        logger.info(
            "pdf_extract_done",
            path=str(path),
            pages=result["pages_processed"],
            tables=len(result["tables"]),
            text_chars=len(result["text"]),
        )
        return result

    def _extract_tables_pdfplumber(self, path: Path) -> List[Dict[str, Any]]:
        tables_out: List[Dict[str, Any]] = []
        with pdfplumber.open(path) as pdf:
            for page_idx, page in enumerate(pdf.pages[: self.max_pages]):
                try:
                    page_tables = page.extract_tables()
                    for t_idx, table in enumerate(page_tables or []):
                        if not table or len(table) < 2:
                            continue
                        # Clean empty rows/cols
                        cleaned = self._clean_table(table)
                        if len(cleaned) < 2:
                            continue
                        df = pd.DataFrame(cleaned[1:], columns=cleaned[0])
                        df = df.dropna(how="all").dropna(axis=1, how="all")
                        if df.empty:
                            continue
                        tables_out.append(
                            {
                                "page": page_idx + 1,
                                "table_index": t_idx,
                                "dataframe": df,
                                "shape": df.shape,
                                "preview": df.head(5).to_dict(orient="records"),
                            }
                        )
                except Exception as e:
                    logger.debug("table_page_failed", page=page_idx, error=str(e))
        return tables_out

    @staticmethod
    def _clean_table(table: List[List[Any]]) -> List[List[str]]:
        cleaned = []
        for row in table:
            cleaned_row = [
                re.sub(r"\s+", " ", str(cell or "")).strip() for cell in row
            ]
            if any(cleaned_row):
                cleaned.append(cleaned_row)
        return cleaned

    def extract_key_indicators(self, text: str) -> Dict[str, Any]:
        """
        Heuristic extraction of common Vietnamese macro indicators from text.
        Used as supplement to LLM extraction.
        """
        indicators: Dict[str, Any] = {}

        patterns = {
            "gdp_growth": [
                r"GDP.*?tăng\s*([\d,\.]+)\s*%",
                r"tăng trưởng.*?GDP.*?([\d,\.]+)\s*%",
                r"GDP.*?([\d,\.]+)\s*%",
            ],
            "cpi": [
                r"CPI.*?([\d,\.]+)\s*%",
                r"lạm phát.*?([\d,\.]+)\s*%",
            ],
            "exchange_rate": [
                r"tỷ giá.*?([\d,\.]+)\s*VND",
                r"([\d,\.]+)\s*VND/USD",
            ],
            "export": [
                r"xuất khẩu.*?([\d,\.]+)\s*(tỷ|tỉ)\s*USD",
            ],
            "import": [
                r"nhập khẩu.*?([\d,\.]+)\s*(tỷ|tỉ)\s*USD",
            ],
            "credit_growth": [
                r"tín dụng.*?tăng\s*([\d,\.]+)\s*%",
            ],
        }

        for key, pats in patterns.items():
            for pat in pats:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    indicators[key] = m.group(1).replace(",", ".")
                    break

        return indicators
