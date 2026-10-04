"""
Research Orchestrator – multi-step professional analysis pipeline.

Pipeline:
  1. Resolve company (ticker / name / MST)
  2. Collect macro snapshot (NSO + NHNN)
  3. Extract / compute financial ratios
  4. Multi-section LLM generation (or single deep pass)
  5. Assemble ResearchReport
  6. Export PDF + Markdown + Excel
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.analysis.prompts import (
    SYSTEM_RESEARCH_ANALYST,
    build_business_overview_prompt,
    build_executive_summary_prompt,
    build_financial_analysis_prompt,
    build_full_report_prompt,
    build_macro_linkage_prompt,
    build_risks_outlook_prompt,
)
from app.analysis.ratios import ratios_from_key_figures, ratios_to_dict
from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.provider import get_llm_provider
from app.models.schemas import (
    CompanyIdentifier,
    CompanyProfile,
    JobStatus,
    MacroSnapshot,
    ResearchDepth,
    ResearchReport,
)
from app.reporting.excel_export import export_excel
from app.reporting.markdown_export import export_markdown
from app.reporting.pdf_generator import generate_research_pdf
from app.tools.company_sources import CompanyDataTool
from app.tools.macro_sources import MacroDataTool

logger = get_logger(__name__)


def _extract_ticker(text: str) -> Optional[str]:
    q = (text or "").upper()
    m = re.search(r"(?:MÃ|MA|TICKER|CỔ PHIẾU|CO PHIEU|STOCK)\s*[:=]?\s*([A-Z0-9]{3,10})", q)
    if m:
        return m.group(1)
    m2 = re.search(r"\b([A-Z]{3,4})\b", q)
    if m2:
        cand = m2.group(1)
        stop = {
            "NSO", "NHNN", "SBV", "GSO", "GDP", "CPI", "USD", "VND",
            "PDF", "API", "URL", "HTTP", "HTML", "JSON", "LLM", "CSV",
            "BCTC", "ROE", "ROA", "EPS", "TTM", "YOY",
        }
        if cand not in stop:
            return cand
    return None


def _fmt_macro(m: MacroSnapshot) -> str:
    lines = [f"Thời điểm: {m.as_of or 'N/A'}"]
    if m.gdp_growth is not None:
        lines.append(f"Tăng trưởng GDP: {m.gdp_growth}%")
    if m.cpi_yoy is not None:
        lines.append(f"CPI YoY: {m.cpi_yoy}%")
    if m.credit_growth is not None:
        lines.append(f"Tăng trưởng tín dụng: {m.credit_growth}%")
    if m.usd_vnd is not None:
        lines.append(f"Tỷ giá USD/VND (trung tâm): {m.usd_vnd:,.0f}")
    if m.fdi_disbursed is not None:
        lines.append(f"FDI giải ngân: {m.fdi_disbursed}")
    for n in m.notes:
        lines.append(f"Ghi chú: {n}")
    return "\n".join(lines) if lines else "Chưa có dữ liệu vĩ mô chi tiết."


def _fmt_dict(d: Dict[str, Any], title: str = "") -> str:
    if not d:
        return f"{title}: (không có)"
    lines = [title] if title else []
    for k, v in d.items():
        lines.append(f"  • {k}: {v}")
    return "\n".join(lines)


class ResearchOrchestrator:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.macro_tool = MacroDataTool()
        self.company_tool = CompanyDataTool()
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            try:
                self._llm = get_llm_provider()
            except Exception as e:
                logger.warning("llm_init_failed", error=str(e))
                self._llm = None
        return self._llm

    def create_job(self, query: str, company: Optional[CompanyIdentifier] = None) -> str:
        job_id = str(uuid.uuid4())
        now = datetime.utcnow()
        self.jobs[job_id] = {
            "job_id": job_id,
            "query": query,
            "company": company.model_dump() if company else None,
            "status": JobStatus.PENDING,
            "message": "Job created",
            "created_at": now,
            "updated_at": now,
            "progress": [],
            "result": None,
            "error": None,
        }
        return job_id

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self.jobs.get(job_id)

    def _progress(self, job: Dict, msg: str) -> None:
        job["progress"].append(msg)
        job["message"] = msg
        job["updated_at"] = datetime.utcnow()
        logger.info("job_progress", job_id=job["job_id"], msg=msg)

    def run(
        self,
        query: str,
        job_id: Optional[str] = None,
        company: Optional[CompanyIdentifier] = None,
        depth: ResearchDepth = ResearchDepth.STANDARD,
        include_macro: bool = True,
        export_pdf: bool = True,
        export_excel: bool = True,
    ) -> Dict[str, Any]:
        if not job_id:
            job_id = self.create_job(query, company)
        job = self.jobs[job_id]
        job["status"] = JobStatus.RUNNING
        self._progress(job, "Bắt đầu pipeline nghiên cứu chuyên sâu...")

        try:
            result = self._execute(
                query=query,
                job=job,
                company=company,
                depth=depth,
                include_macro=include_macro,
                export_pdf=export_pdf,
                export_excel=export_excel,
            )
            job["result"] = result
            job["status"] = JobStatus.SUCCESS if result.get("confidence") != "low" else JobStatus.PARTIAL
            job["message"] = "Hoàn thành báo cáo nghiên cứu"
        except Exception as e:
            logger.exception("research_run_failed", job_id=job_id)
            job["status"] = JobStatus.FAILED
            job["error"] = str(e)
            job["message"] = f"Lỗi: {e}"
        finally:
            job["updated_at"] = datetime.utcnow()
        return job

    def _execute(
        self,
        query: str,
        job: Dict[str, Any],
        company: Optional[CompanyIdentifier],
        depth: ResearchDepth,
        include_macro: bool,
        export_pdf: bool,
        export_excel: bool,
    ) -> Dict[str, Any]:
        # ---- 1. Resolve identity ----
        ticker = None
        name = None
        tax_code = None
        if company:
            ticker = company.ticker
            name = company.name
            tax_code = company.tax_code
        if not ticker:
            ticker = _extract_ticker(query)
        if not name and not ticker:
            # Try to pull a company-like phrase from query
            m = re.search(
                r"(?:công ty|cty|tập đoàn|corporation|company)\s+([A-Za-zÀ-ỹ0-9\s&\.\-]{3,60})",
                query,
                re.I,
            )
            if m:
                name = m.group(1).strip()

        self._progress(job, f"Định danh đối tượng: ticker={ticker}, name={name}, MST={tax_code}")

        company_data = self.company_tool.resolve_company(
            name=name, ticker=ticker, tax_code=tax_code
        )
        profile: Optional[CompanyProfile] = company_data.get("profile")
        company_name = (
            (profile.name if profile else None)
            or company_data.get("company_name")
            or name
            or ticker
            or "Đối tượng nghiên cứu"
        )
        key_figures = company_data.get("key_figures") or {}
        sources = list(company_data.get("sources") or [])

        self._progress(
            job,
            f"Dữ liệu công ty: status={company_data.get('status')}, "
            f"figures={len(key_figures)}, reports={len(company_data.get('reports') or [])}",
        )

        # ---- 2. Macro ----
        macro: Optional[MacroSnapshot] = None
        if include_macro:
            self._progress(job, "Thu thập dữ liệu vĩ mô (NSO + NHNN)...")
            macro = self.macro_tool.collect_snapshot()
            sources.extend(macro.sources or [])

        # ---- 3. Ratios ----
        ratios = ratios_from_key_figures(key_figures)
        ratios_dict = ratios_to_dict(ratios)

        # ---- 4. LLM analysis ----
        self._progress(job, "Sinh báo cáo phân tích chuyên sâu bằng LLM...")
        report_sections = self._generate_sections(
            query=query,
            company_name=company_name,
            profile=profile,
            macro=macro,
            key_figures=key_figures,
            ratios_dict=ratios_dict,
            depth=depth,
        )

        # ---- 5. Assemble ----
        report_id = job["job_id"]
        generated_at = datetime.utcnow()
        title = f"Báo cáo Nghiên cứu: {company_name}"
        if ticker:
            title += f" ({ticker})"

        report_data: Dict[str, Any] = {
            "report_id": report_id,
            "title": title,
            "generated_at": generated_at.strftime("%Y-%m-%d %H:%M UTC"),
            "depth": depth.value,
            "query": query,
            "company_name": company_name,
            "ticker": ticker or (profile.ticker if profile else None),
            "executive_summary": report_sections.get("executive_summary", ""),
            "business_overview": report_sections.get("business_overview", ""),
            "financial_analysis": report_sections.get("financial_analysis", ""),
            "industry_macro_linkage": report_sections.get("industry_macro_linkage", ""),
            "valuation_or_credit": report_sections.get("valuation_or_credit", ""),
            "risks": report_sections.get("risks", ""),
            "outlook_recommendation": report_sections.get("outlook_recommendation", ""),
            "appendix_notes": report_sections.get("appendix_notes", ""),
            "sources": list(dict.fromkeys(sources))[:15],
            "key_figures": key_figures,
            "ratios_dict": ratios_dict,
            "macro_dict": macro.model_dump() if macro else {},
            "confidence": report_sections.get("confidence", "medium"),
        }

        # ---- 6. Export ----
        stamp = generated_at.strftime("%Y%m%d_%H%M%S")
        safe_name = re.sub(r"[^\w\-]", "_", company_name)[:40]
        base = f"{stamp}_{report_id[:8]}_{safe_name}"

        pdf_path = None
        md_path = None
        xlsx_path = None

        if export_pdf:
            self._progress(job, "Xuất PDF chuyên nghiệp...")
            try:
                pdf_path = self.settings.reports_dir / f"{base}_research.pdf"
                generate_research_pdf(report_data, pdf_path)
                report_data["pdf_path"] = str(pdf_path)
            except Exception as e:
                logger.warning("pdf_export_failed", error=str(e))
                report_data["pdf_error"] = str(e)

        self._progress(job, "Xuất Markdown...")
        try:
            md_path = self.settings.reports_dir / f"{base}_research.md"
            export_markdown(report_data, md_path)
            report_data["markdown_path"] = str(md_path)
        except Exception as e:
            logger.warning("md_export_failed", error=str(e))

        if export_excel:
            self._progress(job, "Xuất Excel chỉ số...")
            try:
                xlsx_path = self.settings.reports_dir / f"{base}_chisieu.xlsx"
                export_excel(report_data, xlsx_path)
                report_data["excel_path"] = str(xlsx_path)
            except Exception as e:
                logger.warning("excel_export_failed", error=str(e))

        report_data["download_hints"] = []
        if pdf_path:
            report_data["download_hints"].append(
                f"/api/v1/reports/download/{pdf_path.name}"
            )
        if md_path:
            report_data["download_hints"].append(
                f"/api/v1/reports/download/{md_path.name}"
            )
        if xlsx_path:
            report_data["download_hints"].append(
                f"/api/v1/reports/download/{xlsx_path.name}"
            )

        self._progress(job, "Hoàn tất pipeline.")
        return report_data

    def _generate_sections(
        self,
        query: str,
        company_name: str,
        profile: Optional[CompanyProfile],
        macro: Optional[MacroSnapshot],
        key_figures: Dict[str, Any],
        ratios_dict: Dict[str, Any],
        depth: ResearchDepth,
    ) -> Dict[str, str]:
        """Multi-step or single-pass LLM generation depending on depth & LLM availability."""
        llm = self.llm
        macro_text = _fmt_macro(macro) if macro else "Chưa có dữ liệu vĩ mô."
        kf_text = _fmt_dict(key_figures, "Số liệu chính")
        ratios_text = _fmt_dict(ratios_dict, "Chỉ số tài chính")
        profile_text = ""
        if profile:
            profile_text = (
                f"Tên: {profile.name}\n"
                f"Ticker: {profile.ticker or 'N/A'}\n"
                f"MST: {profile.tax_code or 'N/A'}\n"
                f"Trạng thái: {profile.listing_status}\n"
                f"Ngành: {profile.industry or profile.sector or 'N/A'}\n"
                f"Mô tả: {profile.description or 'N/A'}"
            )
        else:
            profile_text = f"Tên: {company_name}"

        industry = (profile.industry or profile.sector) if profile else ""

        if not llm or not llm.available:
            # Fallback template (still structured, not the old poor one)
            return self._fallback_report(
                query, company_name, macro_text, kf_text, ratios_text, profile_text
            )

        sections: Dict[str, str] = {}

        if depth == ResearchDepth.QUICK:
            # Single condensed pass
            system, user = build_full_report_prompt(
                query, company_name, profile_text, macro_text, kf_text, ratios_text, depth.value
            )
            full = llm.generate(system, user)
            sections["executive_summary"] = full[:1200] if full else ""
            sections["financial_analysis"] = full[1200:2500] if full else ""
            sections["outlook_recommendation"] = full[2500:] if full else ""
            sections["confidence"] = "medium"
            return sections

        # STANDARD / DEEP → multi-section
        # 1. Executive Summary
        sys, usr = build_executive_summary_prompt(
            query, company_name, macro_text, kf_text, depth.value
        )
        sections["executive_summary"] = llm.generate(sys, usr) or ""

        # 2. Business Overview
        sys, usr = build_business_overview_prompt(company_name, profile_text, query)
        sections["business_overview"] = llm.generate(sys, usr) or ""

        # 3. Financial Analysis
        sys, usr = build_financial_analysis_prompt(
            company_name, kf_text, ratios_text, "(chuỗi thời gian hạn chế trong lần chạy này)"
        )
        sections["financial_analysis"] = llm.generate(sys, usr) or ""

        # 4. Macro linkage
        sys, usr = build_macro_linkage_prompt(company_name, industry or "", macro_text)
        sections["industry_macro_linkage"] = llm.generate(sys, usr) or ""

        # 5. Valuation / Credit (simple prompt)
        val_prompt = f"""Viết phần Đánh giá Định giá (nếu là cổ phiếu niêm yết) hoặc Đánh giá Tín dụng (nếu là công ty chưa niêm yết / tín dụng) cho {company_name}.

Số liệu: {kf_text}
Chỉ số: {ratios_text}
Listing: {profile.listing_status if profile else 'unknown'}

Nếu có P/E, P/B → nhận xét định giá tương đối.
Nếu không → tập trung vào khả năng trả nợ, thanh khoản, đòn bẩy.
Độ dài 200–350 từ."""
        sections["valuation_or_credit"] = llm.generate(SYSTEM_RESEARCH_ANALYST, val_prompt) or ""

        # 6. Risks + Outlook
        key_points = (
            sections.get("executive_summary", "")[:400]
            + "\n"
            + sections.get("financial_analysis", "")[:400]
        )
        sys, usr = build_risks_outlook_prompt(company_name, industry or "", macro_text, key_points)
        risks_outlook = llm.generate(sys, usr) or ""
        # Split roughly
        if "### Triển vọng" in risks_outlook or "Triển vọng &" in risks_outlook:
            parts = re.split(r"###?\s*Triển vọng.*", risks_outlook, maxsplit=1)
            sections["risks"] = parts[0].replace("### Rủi ro chính", "").strip()
            sections["outlook_recommendation"] = parts[1].strip() if len(parts) > 1 else ""
        else:
            sections["risks"] = risks_outlook[: len(risks_outlook) // 2]
            sections["outlook_recommendation"] = risks_outlook[len(risks_outlook) // 2 :]

        # Appendix
        sections["appendix_notes"] = (
            f"Dữ liệu được tổng hợp tự động từ nguồn công khai tại thời điểm chạy.\n"
            f"Trạng thái dữ liệu công ty: {profile.listing_status if profile else 'N/A'}.\n"
            f"Số chỉ số tài chính thu thập được: {len(key_figures)}.\n"
            f"Khuyến nghị: nếu có BCTC đầy đủ (Excel/PDF), hãy upload để phân tích sâu hơn."
        )
        sections["confidence"] = "high" if key_figures else "medium"
        return sections

    def _fallback_report(
        self,
        query: str,
        company_name: str,
        macro_text: str,
        kf_text: str,
        ratios_text: str,
        profile_text: str,
    ) -> Dict[str, str]:
        """Structured fallback when LLM is unavailable – still readable Vietnamese report."""
        return {
            "executive_summary": (
                f"Báo cáo nghiên cứu về {company_name} được lập trên cơ sở dữ liệu công khai hiện có. "
                f"Yêu cầu gốc của người dùng: {query}.\n\n"
                "Lưu ý quan trọng: Hệ thống chưa kết nối được LLM (thiếu GROQ_API_KEY hoặc OPENAI_API_KEY, "
                "hoặc gọi API thất bại). Do đó phần phân tích định tính bị giới hạn. "
                "Các số liệu và chỉ số (nếu thu thập được) vẫn được trình bày ở các mục sau. "
                "Khuyến nghị: cấu hình API key và chạy lại, đồng thời bổ sung BCTC chi tiết để nâng chất lượng đánh giá."
            ),
            "business_overview": (
                profile_text
                or f"Thông tin tổng quan về {company_name} còn hạn chế trong lần thu thập tự động này. "
                "Công ty có thể là doanh nghiệp niêm yết hoặc chưa niêm yết; cần đối chiếu hồ sơ đăng ký kinh doanh và website chính thức."
            ),
            "financial_analysis": (
                f"Số liệu chính thu thập được từ nguồn công khai:\n{kf_text}\n\n"
                f"Chỉ số tính toán (nếu có):\n{ratios_text}\n\n"
                "Nhận xét: Phân tích sâu (xu hướng nhiều kỳ, chất lượng lợi nhuận, dòng tiền) cần chuỗi BCTC "
                "3–5 năm và engine LLM. Hiện tại hệ thống chỉ trình bày số liệu thô đã scrape được. "
                "Nếu chỉ số quá ít hoặc bất hợp lý, đó có thể là lỗi parse trang nguồn – "
                "cần cải thiện scraper hoặc nhập BCTC thủ công."
            ),
            "industry_macro_linkage": (
                f"Bối cảnh vĩ mô Việt Nam (NSO / NHNN):\n{macro_text}\n\n"
                "Tác động tới doanh nghiệp phụ thuộc ngành: xuất khẩu nhạy tỷ giá và cầu thế giới; "
                "ngành nội địa nhạy tiêu dùng, lạm phát và tín dụng; ngân hàng / BĐS nhạy lãi suất và chính sách."
            ),
            "valuation_or_credit": (
                "Chưa đủ dữ liệu thị trường (P/E, P/B, EV/EBITDA) hoặc BCTC đầy đủ để đưa ra "
                "định giá cổ phiếu hoặc đánh giá tín dụng định lượng trong lần chạy này. "
                "Khi có đủ số liệu, cần so sánh với trung bình ngành và lịch sử công ty."
            ),
            "risks": (
                "• Rủi ro dữ liệu: thiếu hoặc parse sai BCTC có thể làm sai lệch toàn bộ đánh giá.\n"
                "• Rủi ro vĩ mô: biến động tỷ giá USD/VND, lãi suất, lạm phát, cầu tiêu dùng.\n"
                "• Rủi ro ngành: cạnh tranh, thay đổi chính sách, chu kỳ nguyên liệu.\n"
                "• Rủi ro vận hành / quản trị: cần đánh giá thêm khi có thông tin ban lãnh đạo và cổ đông.\n"
                "• Rủi ro thanh khoản và đòn bẩy: chưa định lượng được nếu thiếu bảng cân đối kế toán."
            ),
            "outlook_recommendation": (
                "Quan điểm tạm thời: Trung lập / Cần thêm dữ liệu.\n\n"
                "Khuyến nghị thao tác:\n"
                "1) Điền GROQ_API_KEY hoặc OPENAI_API_KEY vào biến môi trường và chạy lại.\n"
                "2) Thu thập BCTC 3–5 năm (PDF/Excel) và bổ sung vào hệ thống.\n"
                "3) Sau khi có báo cáo LLM đầy đủ, mới dùng làm tham chiếu đầu tư hoặc tín dụng.\n\n"
                "Báo cáo này chỉ mang tính khung kỹ thuật, không phải khuyến nghị đầu tư."
            ),
            "appendix_notes": (
                "Báo cáo chế độ fallback – LLM không khả dụng trong lần chạy này. "
                "Kiểm tra log server và biến môi trường GROQ_API_KEY / OPENAI_API_KEY."
            ),
            "confidence": "low",
        }
