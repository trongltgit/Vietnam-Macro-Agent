"""Export key figures & ratios to Excel."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)


def export_excel(
    report_data: Dict[str, Any],
    output_path: Path,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    kf = report_data.get("key_figures") or {}
    ratios = report_data.get("ratios_dict") or {}
    macro = report_data.get("macro_dict") or {}

    rows = []
    for k, v in kf.items():
        rows.append({"Nhóm": "Công ty", "Chỉ tiêu": k, "Giá trị": v})
    for k, v in ratios.items():
        rows.append({"Nhóm": "Chỉ số tài chính", "Chỉ tiêu": k, "Giá trị": v})
    for k, v in macro.items():
        if v is not None and not isinstance(v, (list, dict)):
            rows.append({"Nhóm": "Vĩ mô", "Chỉ tiêu": k, "Giá trị": v})

    if not rows:
        rows = [{"Nhóm": "—", "Chỉ tiêu": "(không có dữ liệu)", "Giá trị": ""}]

    df = pd.DataFrame(rows)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Chi_so", index=False)
        # Meta sheet
        meta = pd.DataFrame(
            [
                {"Trường": "Tiêu đề", "Giá trị": report_data.get("title", "")},
                {"Trường": "Công ty", "Giá trị": report_data.get("company_name", "")},
                {"Trường": "Ticker", "Giá trị": report_data.get("ticker", "")},
                {"Trường": "Ngày tạo", "Giá trị": str(report_data.get("generated_at", ""))},
            ]
        )
        meta.to_excel(writer, sheet_name="Meta", index=False)

    logger.info("excel_exported", path=str(output_path))
    return output_path
