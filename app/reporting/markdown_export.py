"""Export research report as clean Markdown."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from app.core.logging import get_logger

logger = get_logger(__name__)


def export_markdown(report_data: Dict[str, Any], output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append(f"# {report_data.get('title', 'Báo cáo Phân tích')}")
    lines.append("")
    lines.append(f"**Đối tượng:** {report_data.get('company_name', '—')}")
    if report_data.get("ticker"):
        lines.append(f"**Mã CK:** {report_data['ticker']}")
    lines.append(f"**Độ sâu:** {report_data.get('depth', 'standard')}")
    lines.append(f"**Ngày tạo:** {report_data.get('generated_at', datetime.utcnow().isoformat())}")
    lines.append("")
    lines.append("---")
    lines.append("")

    sections = [
        ("1. Tóm tắt Điều hành", "executive_summary"),
        ("2. Tổng quan Doanh nghiệp & Mô hình Kinh doanh", "business_overview"),
        ("3. Phân tích Tài chính", "financial_analysis"),
        ("4. Liên kết Vĩ mô – Ngành", "industry_macro_linkage"),
        ("5. Đánh giá Định giá / Tín dụng", "valuation_or_credit"),
        ("6. Rủi ro Chính", "risks"),
        ("7. Triển vọng & Khuyến nghị", "outlook_recommendation"),
        ("8. Phụ lục & Ghi chú Dữ liệu", "appendix_notes"),
    ]

    for title, key in sections:
        body = report_data.get(key) or ""
        if body.strip():
            lines.append(f"## {title}")
            lines.append("")
            lines.append(body.strip())
            lines.append("")

    sources = report_data.get("sources") or []
    if sources:
        lines.append("## Nguồn tham chiếu")
        lines.append("")
        for i, s in enumerate(sources, 1):
            lines.append(f"{i}. {s}")
        lines.append("")

    text = "\n".join(lines)
    output_path.write_text(text, encoding="utf-8")
    logger.info("markdown_exported", path=str(output_path))
    return output_path
