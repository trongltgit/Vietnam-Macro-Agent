"""
Correlation and basic statistical analysis with phase-1 Excel data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.core.logging import get_logger
from app.extractors.excel_extractor import ExcelExtractor

logger = get_logger(__name__)


class CorrelationAnalyzer:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.excel = ExcelExtractor()

    def load_phase1(self, path: Optional[str | Path] = None) -> Dict[str, pd.DataFrame]:
        path = Path(path) if path else self.settings.excel_phase1_path
        if not path.exists():
            logger.warning("phase1_excel_not_found", path=str(path))
            return {}
        data = self.excel.read(path)
        return {name: info["dataframe"] for name, info in data.get("sheets", {}).items()}

    def load_processed_macro(self) -> pd.DataFrame:
        """Load all CSV in processed/macro into one DataFrame if possible."""
        macro_dir = self.settings.processed_dir / "macro"
        frames = []
        if macro_dir.exists():
            for csv in macro_dir.glob("*.csv"):
                try:
                    df = pd.read_csv(csv)
                    df["source_file"] = csv.name
                    frames.append(df)
                except Exception as e:
                    logger.warning("csv_load_failed", file=str(csv), error=str(e))
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def compute_correlation(
        self,
        df: pd.DataFrame,
        method: str = "pearson",
        min_periods: int = 3,
        variables: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if df.empty:
            return {"error": "Empty dataframe", "matrix": None}

        # Select numeric columns
        numeric = df.select_dtypes(include=[np.number])
        if variables:
            cols = [c for c in variables if c in numeric.columns]
            numeric = numeric[cols]

        if numeric.shape[1] < 2:
            return {"error": "Need at least 2 numeric columns", "matrix": None}

        corr = numeric.corr(method=method, min_periods=min_periods)
        # Also return pairwise significant correlations
        pairs = []
        cols = list(corr.columns)
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                val = corr.iloc[i, j]
                if pd.notna(val):
                    pairs.append(
                        {
                            "var1": cols[i],
                            "var2": cols[j],
                            "correlation": round(float(val), 4),
                            "abs": abs(float(val)),
                        }
                    )
        pairs = sorted(pairs, key=lambda x: x["abs"], reverse=True)

        return {
            "method": method,
            "n_variables": numeric.shape[1],
            "n_rows": numeric.shape[0],
            "matrix": corr.round(4).to_dict(),
            "top_pairs": pairs[:20],
        }

    def run_full_analysis(
        self,
        method: str = "pearson",
        variables: Optional[List[str]] = None,
        min_periods: int = 3,
    ) -> Dict[str, Any]:
        """
        Combine phase-1 Excel numeric data + processed macro CSVs
        and compute correlations.
        """
        phase1_sheets = self.load_phase1()
        macro_df = self.load_processed_macro()

        results: Dict[str, Any] = {
            "phase1_sheets": list(phase1_sheets.keys()),
            "macro_rows": len(macro_df),
            "analyses": {},
        }

        # Analyze each phase1 sheet
        for sheet_name, df in phase1_sheets.items():
            results["analyses"][f"phase1_{sheet_name}"] = self.compute_correlation(
                df, method=method, min_periods=min_periods, variables=variables
            )

        # Analyze macro processed
        if not macro_df.empty:
            results["analyses"]["processed_macro"] = self.compute_correlation(
                macro_df, method=method, min_periods=min_periods, variables=variables
            )

        # Try merge common date columns if possible (simple heuristic)
        # User can extend later with their internal logic

        logger.info("analysis_completed", sheets=list(results["analyses"].keys()))
        return results
