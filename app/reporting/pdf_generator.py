"""
Professional PDF research report generator using ReportLab.
Style inspired by commercial bank research notes.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Colors – professional dark blue theme
PRIMARY = colors.HexColor("#0B3D5C")
ACCENT = colors.HexColor("#1A6B9A")
LIGHT_BG = colors.HexColor("#F4F7FA")
MUTED = colors.HexColor("#5A6A7A")
RISK_HIGH = colors.HexColor("#C0392B")
RISK_MED = colors.HexColor("#E67E22")
POSITIVE = colors.HexColor("#1E8449")


def _styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    styles = {
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Title"],
            fontSize=20,
            textColor=PRIMARY,
            alignment=TA_CENTER,
            spaceAfter=8,
            leading=26,
            fontName="Helvetica-Bold",
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            parent=base["Normal"],
            fontSize=11,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=4,
        ),
        "section": ParagraphStyle(
            "section",
            parent=base["Heading1"],
            fontSize=13,
            textColor=PRIMARY,
            spaceBefore=16,
            spaceAfter=8,
            fontName="Helvetica-Bold",
            borderPadding=3,
        ),
        "subsection": ParagraphStyle(
            "subsection",
            parent=base["Heading2"],
            fontSize=11,
            textColor=ACCENT,
            spaceBefore=10,
            spaceAfter=5,
            fontName="Helvetica-Bold",
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontSize=9.5,
            leading=13,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
            fontName="Helvetica",
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=base["Normal"],
            fontSize=9.5,
            leading=12.5,
            leftIndent=12,
            spaceAfter=3,
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=base["Normal"],
            fontSize=7.5,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "meta": ParagraphStyle(
            "meta",
            parent=base["Normal"],
            fontSize=8,
            textColor=MUTED,
            alignment=TA_LEFT,
        ),
        "disclaimer": ParagraphStyle(
            "disclaimer",
            parent=base["Normal"],
            fontSize=7.5,
            textColor=MUTED,
            alignment=TA_JUSTIFY,
            leading=10,
        ),
    }
    return styles


def _header_footer(canvas, doc):
    canvas.saveState()
    settings = get_settings()
    # Header line
    canvas.setStrokeColor(PRIMARY)
    canvas.setLineWidth(1.2)
    canvas.line(1.5 * cm, A4[1] - 1.2 * cm, A4[0] - 1.5 * cm, A4[1] - 1.2 * cm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(1.5 * cm, A4[1] - 1.0 * cm, settings.report_org_name)
    canvas.drawRightString(A4[0] - 1.5 * cm, A4[1] - 1.0 * cm, "Research Note – Confidential")
    # Footer
    canvas.setLineWidth(0.6)
    canvas.line(1.5 * cm, 1.3 * cm, A4[0] - 1.5 * cm, 1.3 * cm)
    canvas.drawCentredString(
        A4[0] / 2,
        0.8 * cm,
        f"Trang {doc.page}  |  {settings.report_disclaimer[:80]}...",
    )
    canvas.restoreState()


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    # Escape basic XML and convert newlines
    if not text:
        text = ""
    safe = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n\n", "<br/><br/>")
        .replace("\n", "<br/>")
    )
    return Paragraph(safe, style)


def _section_block(title: str, body: str, styles: Dict) -> List:
    elements = []
    elements.append(_p(title, styles["section"]))
    elements.append(
        HRFlowable(width="100%", thickness=0.8, color=ACCENT, spaceAfter=6)
    )
    if body:
        # Split long body into paragraphs
        for para in body.split("\n\n"):
            para = para.strip()
            if para:
                elements.append(_p(para, styles["body"]))
    elements.append(Spacer(1, 4))
    return elements


def generate_research_pdf(
    report_data: Dict[str, Any],
    output_path: Path,
) -> Path:
    """
    Generate a professional multi-page research PDF.

    report_data keys expected:
      title, generated_at, company_name, ticker, depth,
      executive_summary, business_overview, financial_analysis,
      industry_macro_linkage, valuation_or_credit, risks,
      outlook_recommendation, appendix_notes, sources,
      macro_dict, ratios_dict, key_figures
    """
    settings = get_settings()
    styles = _styles()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title=report_data.get("title", "Research Report"),
        author=settings.report_org_name,
    )

    story: List = []

    # ========== COVER ==========
    story.append(Spacer(1, 1.5 * cm))
    story.append(_p("VIETNAM RESEARCH DESK", styles["cover_sub"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(_p(report_data.get("title", "Báo cáo Phân tích"), styles["cover_title"]))
    story.append(Spacer(1, 0.4 * cm))

    meta_lines = []
    if report_data.get("company_name"):
        meta_lines.append(f"<b>Đối tượng:</b> {report_data['company_name']}")
    if report_data.get("ticker"):
        meta_lines.append(f"<b>Mã CK:</b> {report_data['ticker']}")
    meta_lines.append(f"<b>Độ sâu:</b> {report_data.get('depth', 'standard').upper()}")
    gen = report_data.get("generated_at") or datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    meta_lines.append(f"<b>Ngày tạo:</b> {gen}")
    for line in meta_lines:
        story.append(_p(line, styles["cover_sub"]))

    story.append(Spacer(1, 0.6 * cm))
    story.append(
        HRFlowable(width="60%", thickness=1.5, color=PRIMARY, spaceBefore=4, spaceAfter=12)
    )

    # ========== BODY SECTIONS ==========
    sections = [
        ("1. TÓM TẮT ĐIỀU HÀNH", report_data.get("executive_summary", "")),
        ("2. TỔNG QUAN DOANH NGHIỆP & MÔ HÌNH KINH DOANH", report_data.get("business_overview", "")),
        ("3. PHÂN TÍCH TÀI CHÍNH", report_data.get("financial_analysis", "")),
        ("4. LIÊN KẾT VĨ MÔ – NGÀNH", report_data.get("industry_macro_linkage", "")),
        ("5. ĐÁNH GIÁ ĐỊNH GIÁ / TÍN DỤNG", report_data.get("valuation_or_credit", "")),
        ("6. RỦI RO CHÍNH", report_data.get("risks", "")),
        ("7. TRIỂN VỌNG & KHUYẾN NGHỊ", report_data.get("outlook_recommendation", "")),
        ("8. PHỤ LỤC & GHI CHÚ DỮ LIỆU", report_data.get("appendix_notes", "")),
    ]

    for title, body in sections:
        if body and body.strip():
            story.extend(_section_block(title, body, styles))

    # ========== KEY FIGURES TABLE (if any) ==========
    kf = report_data.get("key_figures") or {}
    ratios = report_data.get("ratios_dict") or {}
    if kf or ratios:
        story.append(_p("9. BẢNG CHỈ SỐ TÓM TẮT", styles["section"]))
        story.append(HRFlowable(width="100%", thickness=0.8, color=ACCENT, spaceAfter=6))
        rows = [["Chỉ tiêu", "Giá trị"]]
        for k, v in {**kf, **ratios}.items():
            rows.append([str(k), str(v)])
        if len(rows) > 1:
            t = Table(rows, colWidths=[9 * cm, 6 * cm])
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.append(t)
            story.append(Spacer(1, 10))

    # ========== SOURCES ==========
    sources = report_data.get("sources") or []
    if sources:
        story.append(_p("NGUỒN THAM CHIẾU", styles["subsection"]))
        for i, s in enumerate(sources[:12], 1):
            story.append(_p(f"{i}. {s}", styles["meta"]))

    story.append(Spacer(1, 12))
    story.append(
        HRFlowable(width="100%", thickness=0.5, color=MUTED, spaceBefore=4, spaceAfter=6)
    )
    story.append(_p(settings.report_disclaimer, styles["disclaimer"]))

    try:
        doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
        logger.info("pdf_generated", path=str(output_path))
        return output_path
    except Exception as e:
        logger.exception("pdf_generation_failed", error=str(e))
        raise
