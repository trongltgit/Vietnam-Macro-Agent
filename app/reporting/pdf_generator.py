"""
Professional PDF research report generator using ReportLab.
Uses DejaVu Sans for full Vietnamese Unicode support.
Style inspired by commercial bank research notes.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

PRIMARY = colors.HexColor("#0B3D5C")
ACCENT = colors.HexColor("#1A6B9A")
LIGHT_BG = colors.HexColor("#F4F7FA")
MUTED = colors.HexColor("#5A6A7A")

_FONTS_REGISTERED = False
# Module-level font names, set by _register_fonts()
FONT_REG = "Helvetica"
FONT_BOLD = "Helvetica-Bold"


def _register_fonts() -> None:
    global _FONTS_REGISTERED, FONT_REG, FONT_BOLD
    if _FONTS_REGISTERED:
        return

    candidates = [
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "DejaVuSans",
            "DejaVuSans-Bold",
        ),
        (
            str(Path(__file__).resolve().parents[2] / "fonts" / "DejaVuSans.ttf"),
            str(Path(__file__).resolve().parents[2] / "fonts" / "DejaVuSans-Bold.ttf"),
            "DejaVuSans",
            "DejaVuSans-Bold",
        ),
    ]

    for reg_path, bold_path, reg_name, bold_name in candidates:
        if Path(reg_path).exists() and Path(bold_path).exists():
            try:
                pdfmetrics.registerFont(TTFont(reg_name, reg_path))
                pdfmetrics.registerFont(TTFont(bold_name, bold_path))
                FONT_REG = reg_name
                FONT_BOLD = bold_name
                _FONTS_REGISTERED = True
                logger.info("pdf_fonts_registered", regular=reg_path)
                return
            except Exception as e:
                logger.warning("pdf_font_register_failed", path=reg_path, error=str(e))

    logger.warning("pdf_fonts_missing_vietnamese_support_using_helvetica")
    FONT_REG = "Helvetica"
    FONT_BOLD = "Helvetica-Bold"
    _FONTS_REGISTERED = True


def _styles() -> Dict[str, ParagraphStyle]:
    _register_fonts()
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Title"],
            fontSize=18,
            textColor=PRIMARY,
            alignment=TA_CENTER,
            spaceAfter=8,
            leading=24,
            fontName=FONT_BOLD,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            parent=base["Normal"],
            fontSize=10,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=3,
            fontName=FONT_REG,
            leading=13,
        ),
        "section": ParagraphStyle(
            "section",
            parent=base["Heading1"],
            fontSize=12,
            textColor=PRIMARY,
            spaceBefore=14,
            spaceAfter=6,
            fontName=FONT_BOLD,
            leading=16,
        ),
        "subsection": ParagraphStyle(
            "subsection",
            parent=base["Heading2"],
            fontSize=10.5,
            textColor=ACCENT,
            spaceBefore=8,
            spaceAfter=4,
            fontName=FONT_BOLD,
            leading=14,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontSize=9.5,
            leading=13.5,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
            fontName=FONT_REG,
        ),
        "meta": ParagraphStyle(
            "meta",
            parent=base["Normal"],
            fontSize=8,
            textColor=MUTED,
            alignment=TA_LEFT,
            fontName=FONT_REG,
            leading=11,
        ),
        "disclaimer": ParagraphStyle(
            "disclaimer",
            parent=base["Normal"],
            fontSize=7.5,
            textColor=MUTED,
            alignment=TA_JUSTIFY,
            leading=10,
            fontName=FONT_REG,
        ),
        "table_cell": ParagraphStyle(
            "table_cell",
            parent=base["Normal"],
            fontSize=8,
            fontName=FONT_REG,
            leading=11,
        ),
        "table_header": ParagraphStyle(
            "table_header",
            parent=base["Normal"],
            fontSize=8,
            fontName=FONT_BOLD,
            textColor=colors.white,
            leading=11,
        ),
    }


def _header_footer(canvas, doc):
    _register_fonts()
    canvas.saveState()
    settings = get_settings()
    canvas.setStrokeColor(PRIMARY)
    canvas.setLineWidth(1.2)
    canvas.line(1.5 * cm, A4[1] - 1.2 * cm, A4[0] - 1.5 * cm, A4[1] - 1.2 * cm)
    canvas.setFont(FONT_REG, 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(1.5 * cm, A4[1] - 1.0 * cm, settings.report_org_name)
    canvas.drawRightString(A4[0] - 1.5 * cm, A4[1] - 1.0 * cm, "Research Note – Confidential")
    canvas.setLineWidth(0.6)
    canvas.line(1.5 * cm, 1.3 * cm, A4[0] - 1.5 * cm, 1.3 * cm)
    disc = settings.report_disclaimer[:70]
    canvas.drawCentredString(A4[0] / 2, 0.8 * cm, f"Trang {doc.page}  |  {disc}...")
    canvas.restoreState()


def _escape(text: str) -> str:
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    safe = _escape(text).replace("\n\n", "<br/><br/>").replace("\n", "<br/>")
    return Paragraph(safe, style)


def _section_block(title: str, body: str, styles: Dict) -> List:
    elements = []
    elements.append(_p(title, styles["section"]))
    elements.append(HRFlowable(width="100%", thickness=0.8, color=ACCENT, spaceAfter=6))
    if body and body.strip():
        for para in body.split("\n\n"):
            para = para.strip()
            if para:
                elements.append(_p(para, styles["body"]))
    elements.append(Spacer(1, 4))
    return elements


def generate_research_pdf(report_data: Dict[str, Any], output_path: Path) -> Path:
    """Generate professional multi-page research PDF with Vietnamese support."""
    _register_fonts()
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

    # COVER
    story.append(Spacer(1, 1.2 * cm))
    story.append(_p("VIETNAM RESEARCH DESK", styles["cover_sub"]))
    story.append(Spacer(1, 0.25 * cm))
    story.append(_p(report_data.get("title", "Báo cáo Phân tích"), styles["cover_title"]))
    story.append(Spacer(1, 0.35 * cm))

    company_name = report_data.get("company_name") or "—"
    ticker = report_data.get("ticker") or ""
    depth = str(report_data.get("depth", "standard")).upper()
    gen = report_data.get("generated_at") or datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    story.append(_p(f"Đối tượng: {company_name}", styles["cover_sub"]))
    if ticker:
        story.append(_p(f"Mã chứng khoán: {ticker}", styles["cover_sub"]))
    story.append(_p(f"Độ sâu: {depth}", styles["cover_sub"]))
    story.append(_p(f"Ngày tạo: {gen}", styles["cover_sub"]))

    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width="60%", thickness=1.5, color=PRIMARY, spaceBefore=4, spaceAfter=12))

    empty_note = (
        "Chưa có nội dung phân tích cho mục này trong lần chạy hiện tại. "
        "Nguyên nhân thường gặp: thiếu API key LLM (GROQ_API_KEY / OPENAI_API_KEY), "
        "hoặc dữ liệu công ty hạn chế trên nguồn công khai. "
        "Hãy cấu hình API key và chạy lại, hoặc bổ sung BCTC chi tiết."
    )

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
        content = (body or "").strip() or empty_note
        story.extend(_section_block(title, content, styles))

    # KEY FIGURES TABLE
    kf = report_data.get("key_figures") or {}
    ratios = report_data.get("ratios_dict") or {}
    merged = {**kf, **ratios}
    if merged:
        story.append(_p("9. BẢNG CHỈ SỐ TÓM TẮT", styles["section"]))
        story.append(HRFlowable(width="100%", thickness=0.8, color=ACCENT, spaceAfter=6))
        header = [
            Paragraph("Chỉ tiêu", styles["table_header"]),
            Paragraph("Giá trị", styles["table_header"]),
        ]
        rows = [header]
        for k, v in merged.items():
            rows.append([
                Paragraph(_escape(str(k)), styles["table_cell"]),
                Paragraph(_escape(str(v)), styles["table_cell"]),
            ])
        t = Table(rows, colWidths=[9 * cm, 6 * cm])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 10))

    sources = report_data.get("sources") or []
    if sources:
        story.append(_p("NGUỒN THAM CHIẾU", styles["subsection"]))
        for i, s in enumerate(sources[:12], 1):
            story.append(_p(f"{i}. {s}", styles["meta"]))

    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MUTED, spaceBefore=4, spaceAfter=6))
    story.append(_p(settings.report_disclaimer, styles["disclaimer"]))

    try:
        doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
        logger.info("pdf_generated", path=str(output_path), size=output_path.stat().st_size)
        return output_path
    except Exception as e:
        logger.exception("pdf_generation_failed", error=str(e))
        raise
