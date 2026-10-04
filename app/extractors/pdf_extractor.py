"""PDF text + table extractor with key-indicator helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class PDFExtractor:
    def extract(self, file_path: str | Path, max_pages: int = 30) -> Dict[str, Any]:
        path = Path(file_path)
        result: Dict[str, Any] = {
            "file": str(path),
            "text": "",
            "tables": [],
            "pages_processed": 0,
            "metadata": {},
        }
        if not path.exists():
            result["error"] = f"File not found: {path}"
            return result

        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            meta = reader.metadata or {}
            result["metadata"] = {k: str(v) for k, v in dict(meta).items()} if meta else {}
            pages = min(len(reader.pages), max_pages)
            chunks: List[str] = []
            for i in range(pages):
                t = reader.pages[i].extract_text() or ""
                if t.strip():
                    chunks.append(f"--- Page {i+1} ---\n{t}")
            result["text"] = "\n".join(chunks)
            result["pages_processed"] = pages
        except Exception as e:
            logger.exception("pdf_extract_failed", path=str(path))
            result["error"] = str(e)

        # Optional: try pdfplumber tables if available
        try:
            import pdfplumber
            with pdfplumber.open(str(path)) as pdf:
                for pi, page in enumerate(pdf.pages[:max_pages]):
                    for ti, table in enumerate(page.extract_tables() or []):
                        if not table or len(table) < 2:
                            continue
                        try:
                            import pandas as pd
                            header = [str(c or f"col{j}") for j, c in enumerate(table[0])]
                            rows = table[1:]
                            df = pd.DataFrame(rows, columns=header)
                            result["tables"].append({
                                "page": pi + 1,
                                "table_index": ti,
                                "dataframe": df,
                                "shape": df.shape,
                                "preview": df.head(5).to_dict(orient="records"),
                            })
                        except Exception:
                            pass
        except ImportError:
            pass
        except Exception as e:
            logger.warning("pdfplumber_tables_failed", error=str(e))

        return result

    def extract_key_indicators(self, text: str) -> Dict[str, str]:
        inds: Dict[str, str] = {}
        if not text:
            return inds
        patterns = {
            "gdp_growth_pct": r"GDP[^\d]{0,40}(?:tăng|đạt)?[^\d]{0,20}(\d+[.,]\d+)\s*%",
            "cpi_pct": r"CPI[^\d]{0,40}(\d+[.,]\d+)\s*%",
            "credit_growth_pct": r"tín dụng[^\d]{0,40}(\d+[.,]\d+)\s*%",
            "usd_vnd": r"USD[^\d]{0,20}(\d{1,3}[.,]\d{3})",
            "exports": r"xuất khẩu[^\d]{0,40}(\d+[.,]?\d*)\s*(?:tỷ|tỉ|USD|USD)",
            "imports": r"nhập khẩu[^\d]{0,40}(\d+[.,]?\d*)\s*(?:tỷ|tỉ|USD)",
        }
        for key, pat in patterns.items():
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                inds[key] = m.group(1).replace(",", ".")
        return inds

    # backward-compat alias
    @staticmethod
    def extract_text_from_pdf(file_path: str, max_pages: int = 25) -> str:
        return PDFExtractor().extract(file_path, max_pages).get("text", "")
