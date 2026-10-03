"""
Pipeline to merge extracted / processed data into phase-1 Excel workbook.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from app.core.config import get_settings
from app.core.logging import get_logger
from app.extractors.excel_extractor import ExcelExtractor

logger = get_logger(__name__)


class ExcelMergePipeline:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.excel = ExcelExtractor()

    def collect_processed_frames(self) -> Dict[str, pd.DataFrame]:
        """Collect all CSV from processed/ into named DataFrames."""
        frames: Dict[str, pd.DataFrame] = {}
        processed = self.settings.processed_dir

        for sub in ["macro", "exchange_rate", "trade"]:
            folder = processed / sub
            if not folder.exists():
                continue
            for csv in folder.glob("*.csv"):
                try:
                    df = pd.read_csv(csv)
                    # Sheet name from folder + file stem (max 31 chars)
                    name = f"{sub}_{csv.stem}"[:31]
                    frames[name] = df
                except Exception as e:
                    logger.warning("collect_csv_failed", file=str(csv), error=str(e))
        return frames

    def merge(
        self,
        target_path: Optional[str | Path] = None,
        extra_frames: Optional[Dict[str, pd.DataFrame]] = None,
        sheet_prefix: str = "Ext_",
    ) -> Dict[str, Any]:
        """
        Merge processed data into the phase-1 Excel file.
        Creates new sheets with prefix to avoid overwriting internal sheets.
        """
        target = Path(target_path) if target_path else self.settings.excel_phase1_path
        frames = self.collect_processed_frames()
        if extra_frames:
            frames.update(extra_frames)

        if not frames:
            return {
                "status": "empty",
                "message": "No processed data to merge",
                "target": str(target),
            }

        # Prefix sheet names to protect phase-1 internal sheets
        safe_frames = {f"{sheet_prefix}{k}"[:31]: v for k, v in frames.items()}

        # If target does not exist, create a starter workbook
        if not target.exists():
            # Create minimal phase-1 structure
            starter = {
                "Internal": pd.DataFrame({"note": ["Place your internal data here"]}),
                "README": pd.DataFrame(
                    {
                        "info": [
                            "This workbook is managed by Vietnam Macro AI Agent.",
                            "Sheets starting with Ext_ are external macro data.",
                            f"Last merge: {datetime.utcnow().isoformat()}",
                        ]
                    }
                ),
            }
            starter.update(safe_frames)
            path = self.excel.merge_into_workbook(starter, target, overwrite_sheets=True)
        else:
            path = self.excel.merge_into_workbook(safe_frames, target, overwrite_sheets=False)

        return {
            "status": "ok",
            "target": path,
            "sheets_added": list(safe_frames.keys()),
            "merged_at": datetime.utcnow().isoformat(),
        }
