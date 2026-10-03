"""
Excel / CSV extractor and writer utilities.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)


class ExcelExtractor:
    """Read and write Excel / CSV files safely."""

    def read(self, file_path: str | Path, sheet_name: Optional[str] = None) -> Dict[str, Any]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        suffix = path.suffix.lower()
        result: Dict[str, Any] = {"file": str(path), "sheets": {}}

        if suffix == ".csv":
            df = pd.read_csv(path)
            result["sheets"]["Sheet1"] = {
                "dataframe": df,
                "shape": df.shape,
                "columns": list(df.columns),
            }
        elif suffix in {".xlsx", ".xls", ".xlsm"}:
            xl = pd.ExcelFile(path)
            sheets = [sheet_name] if sheet_name else xl.sheet_names
            for s in sheets:
                try:
                    df = pd.read_excel(path, sheet_name=s)
                    result["sheets"][s] = {
                        "dataframe": df,
                        "shape": df.shape,
                        "columns": list(df.columns),
                    }
                except Exception as e:
                    logger.warning("excel_sheet_read_failed", sheet=s, error=str(e))
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

        logger.info("excel_read_done", path=str(path), sheets=list(result["sheets"].keys()))
        return result

    def write_dataframe(
        self,
        df: pd.DataFrame,
        file_path: str | Path,
        sheet_name: str = "Data",
        mode: str = "a",  # 'w' overwrite whole file, 'a' append/replace sheet
    ) -> str:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if mode == "w" or not path.exists():
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        else:
            # Append / replace specific sheet
            with pd.ExcelWriter(
                path,
                engine="openpyxl",
                mode="a",
                if_sheet_exists="replace",
            ) as writer:
                df.to_excel(writer, sheet_name=sheet_name, index=False)

        logger.info("excel_write_done", path=str(path), sheet=sheet_name, rows=len(df))
        return str(path)

    def merge_into_workbook(
        self,
        source_dfs: Dict[str, pd.DataFrame],
        target_path: str | Path,
        overwrite_sheets: bool = False,
    ) -> str:
        """
        Merge multiple DataFrames into an existing or new workbook.
        Does NOT delete other sheets unless overwrite_sheets=True for that sheet.
        """
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists() and not overwrite_sheets:
            mode = "a"
            if_sheet_exists = "replace"
        else:
            mode = "w"
            if_sheet_exists = None

        with pd.ExcelWriter(
            target,
            engine="openpyxl",
            mode=mode,
            if_sheet_exists=if_sheet_exists,
        ) as writer:
            for sheet_name, df in source_dfs.items():
                df.to_excel(writer, sheet_name=sheet_name[:31], index=False)  # Excel sheet name limit

        logger.info(
            "excel_merge_done",
            path=str(target),
            sheets=list(source_dfs.keys()),
        )
        return str(target)
