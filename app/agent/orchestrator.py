"""
Agent: thu thập số liệu → LUÔN viết báo cáo chữ (template) → xuất CSV/MD.
Không trả danh sách URL cho người dùng.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from app.agent.tools.official_sources import OfficialSourceTool
from app.core.config import get_settings
from app.core.logging import get_logger
from app.extractors.pdf_extractor import PDFExtractor
from app.llm.provider import get_llm_provider
from app.models.schemas import JobStatus

logger = get_logger(__name__)


def _extract_ticker(query: str) -> Optional[str]:
    q = (query or "").upper()
    m = re.search(r"(?:MÃ|MA|TICKER|CỔ PHIẾU|CO PHIEU|STOCK)\s*[:=]?\s*([A-Z0-9]{3,10})", q)
    if m:
        return m.group(1)
    m2 = re.search(r"\b([A-Z]{3,4})\b", q)
    if m2:
        cand = m2.group(1)
        stop = {
            "NSO", "NHNN", "SBV", "GSO", "GDP", "CPI", "USD", "VND",
            "PDF", "API", "URL", "HTTP", "HTML", "JSON", "LLM", "CSV", "XLS", "BCTC",
        }
        if cand not in stop:
            return cand
    return None


class AgentOrchestrator:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.source_tool = OfficialSourceTool()
        self.pdf_extractor = PDFExtractor()
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

    def create_job(self, query: str, ticker: Optional[str] = None) -> str:
        job_id = str(uuid.uuid4())
        now = datetime.utcnow()
        self.jobs[job_id] = {
            "job_id": job_id,
            "query": query,
            "ticker": ticker,
            "status": JobStatus.PENDING,
            "message": "Job created",
            "created_at": now,
            "updated_at": now,
            "result": None,
            "error": None,
            "steps": [],
        }
        return job_id

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self.jobs.get(job_id)

    def run(
        self,
        query: str,
        job_id: Optional[str] = None,
        ticker: Optional[str] = None,
    ) -> Dict[str, Any]:
        if job_id is None:
            job_id = self.create_job(query, ticker=ticker)
        job = self.jobs[job_id]
        job["status"] = JobStatus.RUNNING
        job["updated_at"] = datetime.utcnow()
        job["message"] = "Agent is running"
        if ticker:
            job["ticker"] = ticker
        try:
            result = self._execute(query, job, ticker=ticker or job.get("ticker"))
            job["status"] = JobStatus.SUCCESS
            job["result"] = result
            job["message"] = "Completed successfully"
        except Exception as e:
            logger.exception("agent_run_failed", job_id=job_id)
            job["status"] = JobStatus.FAILED
            job["error"] = str(e)
            job["message"] = f"Failed: {e}"
        finally:
            job["updated_at"] = datetime.utcnow()
        return job

    def _execute(
        self,
        query: str,
        job: Dict[str, Any],
        ticker: Optional[str] = None,
    ) -> Dict[str, Any]:
        steps: List[Dict[str, Any]] = []
        if not ticker:
            ticker = _extract_ticker(query)

        # --- Collect data ---
        bundle = self.source_tool.collect_macro_bundle()
        fx = bundle.get("exchange_rate") or {}
        nso = bundle.get("nso_latest") or {}
        steps.append({
            "step": "collect_macro",
            "fx": fx.get("status"),
            "nso": nso.get("status"),
        })

        company_data: Optional[Dict[str, Any]] = None
        if ticker:
            company_data = self.source_tool.fetch_company_reports(ticker)
            steps.append({
                "step": "company",
                "ticker": ticker,
                "status": (company_data or {}).get("status"),
            })

        # Flatten indicators
        indicators: Dict[str, Any] = {}
        if fx.get("rates"):
            indicators["ty_gia_usd_vnd"] = fx["rates"].get("usd_vnd_central")
        for k, v in (nso.get("indicators") or {}).items():
            indicators[k] = v
        if company_data and company_data.get("key_figures"):
            indicators["ma_ck"] = ticker
            indicators["ten_cty"] = company_data.get("company_name")
            for k, v in company_data["key_figures"].items():
                indicators[f"cty_{k}"] = v

        # --- ALWAYS build narrative report (no URLs) ---
        report = self._write_report(
            query=query,
            indicators=indicators,
            ticker=ticker,
            company_data=company_data,
            fx_ok=fx.get("status") == "ok",
            nso_ok=nso.get("status") in ("ok", "partial"),
        )

        # Optional: LLM polish ONLY the report text (strip any URLs it adds)
        report = self._maybe_polish(report, query)

        status = "success" if indicators else "partial"
        notes = []
        if not indicators:
            notes.append("Chưa lấy được chỉ số số học trong lần chạy này.")
        if not fx_ok if False else fx.get("status") != "ok":
            notes.append("Tỷ giá: dùng nguồn tham chiếu hoặc chưa có.")
        if nso.get("status") not in ("ok", "partial"):
            notes.append("NSO: chưa lấy được báo cáo chi tiết.")
        if ticker and not (company_data or {}).get("key_figures"):
            notes.append(f"Chưa trích được số BCTC chi tiết cho {ticker}.")

        exports = self._export_files(job["job_id"], report, indicators, ticker)

        job["steps"] = steps

        # Response for user — NO sources URL list
        return {
            "status": status,
            "report": report,
            "summary": report[:400] + ("…" if len(report) > 400 else ""),
            "indicators": indicators,
            "notes": " ".join(notes) if notes else "Báo cáo đã tạo từ số liệu thu thập được.",
            "exports": exports,
        }

    def _write_report(
        self,
        query: str,
        indicators: Dict[str, Any],
        ticker: Optional[str],
        company_data: Optional[Dict[str, Any]],
        fx_ok: bool,
        nso_ok: bool,
    ) -> str:
        """Báo cáo chữ bắt buộc — không có URL."""
        L: List[str] = []
        L.append("BÁO CÁO TỔNG HỢP KINH TẾ VĨ MÔ & DOANH NGHIỆP")
        L.append("=" * 52)
        L.append(f"Yêu cầu: {query}")
        L.append(f"Thời điểm: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
        L.append("")

        L.append("1. BỐI CẢNH VĨ MÔ THẾ GIỚI")
        L.append("-" * 40)
        L.append(
            "Kinh tế toàn cầu tiếp tục chịu ảnh hưởng từ chính sách tiền tệ các nền "
            "kinh tế lớn, biến động giá hàng hóa và chuỗi cung ứng. Diễn biến này tác "
            "động tới xuất nhập khẩu, tỷ giá và dòng vốn vào Việt Nam. Phần định lượng "
            "chi tiết quốc tế không nằm trong bộ số liệu NSO/NHNN của lần thu thập này; "
            "các kết luận dưới đây dựa trên số liệu trong nước đã có."
        )
        L.append("")

        L.append("2. VĨ MÔ VIỆT NAM")
        L.append("-" * 40)
        labels = {
            "gdp_growth_pct": "Tăng trưởng GDP (%)",
            "gdp_growth_q3_2026_pct": "GDP quý III/2026 (%)",
            "gdp_growth_9m_2026_pct": "GDP 9 tháng/2026 (%)",
            "cpi_pct": "CPI (%)",
            "cpi_month9_2026_pct": "CPI tháng 9/2026 (%)",
            "credit_growth_pct": "Tăng trưởng tín dụng (%)",
            "exports": "Xuất khẩu",
            "exports_growth_pct": "Tăng trưởng xuất khẩu (%)",
            "imports": "Nhập khẩu",
            "imports_growth_pct": "Tăng trưởng nhập khẩu (%)",
            "trade_balance": "Cán cân thương mại",
            "trade_balance_pct": "Cán cân thương mại",
            "ty_gia_usd_vnd": "Tỷ giá USD/VND (tham chiếu)",
            "exchange_rate_usd_vnd": "Tỷ giá USD/VND",
            "exchange_rate_usd_vnd_central": "Tỷ giá trung tâm USD/VND",
        }
        shown = False
        for key, label in labels.items():
            if key in indicators and indicators[key] not in (None, "", "null"):
                L.append(f"  • {label}: {indicators[key]}")
                shown = True
        if not shown:
            L.append("  • Chưa có chỉ tiêu số trong lần chạy này.")
        L.append("")
        if nso_ok:
            L.append(
                "Số liệu vĩ mô trên được tổng hợp từ báo cáo tình hình kinh tế - xã hội "
                "(NSO). Có thể dùng làm biến ngoại sinh khi phân tích cùng dữ liệu MBNT "
                "và TTQT-TTTM trên Excel phase 1."
            )
        if fx_ok:
            L.append(
                "Tỷ giá USD/VND ở trên là mức tham chiếu đã thu thập được tại thời điểm chạy."
            )
        L.append("")

        L.append("3. CÁC NGÀNH CHÍNH")
        L.append("-" * 40)
        L.append(
            "Trên nền tăng trưởng GDP và tín dụng như mục 2, các nhóm ngành xuất khẩu "
            "(điện tử, dệt may, nông sản chế biến) thường nhạy với cầu thế giới và tỷ giá; "
            "nhóm tài chính – ngân hàng nhạy với tín dụng và lãi suất. Để đo quan hệ thực "
            "tế với doanh số thanh toán quốc tế, nên đối chiếu biến XK/NK (sheet TTQT-TTTM) "
            "và DS/LN MBNT theo tháng trên Excel của bạn."
        )
        L.append("")

        L.append("4. DOANH NGHIỆP")
        L.append("-" * 40)
        if ticker:
            name = (company_data or {}).get("company_name") or ticker
            L.append(f"  Mã theo dõi: {ticker}")
            L.append(f"  Tên: {name}")
            figs = (company_data or {}).get("key_figures") or {}
            if figs:
                for k, v in figs.items():
                    L.append(f"  • {k}: {v}")
            else:
                L.append(
                    "  Chưa trích xuất được số liệu BCTC chi tiết (doanh thu, lợi nhuận, EPS) "
                    "từ trang công khai trong lần chạy này. Bạn có thể bổ sung thủ công vào "
                    "sheet Macro_External trên Excel."
                )
        else:
            L.append("  Không có mã chứng khoán trong yêu cầu — bỏ qua phần BCTC.")
        L.append("")

        L.append("5. KẾT LUẬN & HƯỚNG PHÂN TÍCH TIẾP")
        L.append("-" * 40)
        L.append(
            "Báo cáo này cung cấp khung số liệu vĩ mô (và doanh nghiệp nếu có) để nạp vào "
            "Excel phase 1. File CSV kèm theo (exports) nên import vào sheet Macro_External, "
            "sau đó dùng Python trong Excel để tính tương quan giữa các chỉ tiêu vĩ mô với "
            "DS/LN MBNT và XK/NK TTQT-TTTM theo kỳ."
        )
        L.append("")
        L.append("— Hết báo cáo —")
        return "\n".join(L)

    def _maybe_polish(self, report: str, query: str) -> str:
        """LLM chỉ được phép viết lại cho mượt; mọi URL sẽ bị xóa."""
        if not self.llm:
            return report
        try:
            polished = self.llm.chat(
                "Bạn là biên tập báo cáo kinh tế. Viết lại báo cáo cho mạch lạc, "
                "giữ nguyên mọi con số, KHÔNG thêm URL/link, KHÔNG thêm số liệu mới. "
                "Chỉ trả về nội dung báo cáo thuần túy.",
                f"Yêu cầu gốc: {query}\n\nBáo cáo nháp:\n{report[:8000]}",
            )
            polished = (polished or "").strip()
            # Remove any URLs LLM might insert
            polished = re.sub(r"https?://\S+", "", polished)
            polished = re.sub(r"\n{3,}", "\n\n", polished).strip()
            if len(polished) >= 300:
                return polished
        except Exception as e:
            logger.warning("polish_failed", error=str(e))
        return report

    def _export_files(
        self,
        job_id: str,
        report_text: str,
        indicators: Dict[str, Any],
        ticker: Optional[str],
    ) -> Dict[str, Any]:
        out_dir = self.settings.processed_dir / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        base = f"{stamp}_{job_id[:8]}"
        if ticker:
            base += f"_{ticker}"

        md_path = out_dir / f"{base}_baocao.txt"
        csv_path = out_dir / f"{base}_chisieu.csv"
        xlsx_path = out_dir / f"{base}_chisieu.xlsx"

        md_path.write_text(report_text or "", encoding="utf-8")

        rows = []
        for k, v in (indicators or {}).items():
            rows.append({
                "Chi_tieu": k,
                "Gia_tri": v if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False),
                "Ticker": ticker or "",
                "Job": job_id,
            })
        df = pd.DataFrame(rows) if rows else pd.DataFrame(
            {"Chi_tieu": ["(trống)"], "Gia_tri": [""], "Ticker": [ticker or ""], "Job": [job_id]}
        )
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        try:
            df.to_excel(xlsx_path, index=False)
            xlsx_ok = True
        except Exception:
            xlsx_ok = False

        hints = [
            f"/api/v1/reports/download-processed/reports/{md_path.name}",
            f"/api/v1/reports/download-processed/reports/{csv_path.name}",
        ]
        if xlsx_ok:
            hints.append(f"/api/v1/reports/download-processed/reports/{xlsx_path.name}")

        return {
            "report_file": str(md_path),
            "indicators_csv": str(csv_path),
            "indicators_xlsx": str(xlsx_path) if xlsx_ok else None,
            "download_hints": hints,
        }
