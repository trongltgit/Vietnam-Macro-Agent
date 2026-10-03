"""
Agent orchestrator — fetch NHNN/NSO data then summarize with LLM.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agent.tools.official_sources import OfficialSourceTool
from app.core.config import get_settings
from app.core.logging import get_logger
from app.extractors.excel_extractor import ExcelExtractor
from app.extractors.pdf_extractor import PDFExtractor
from app.llm.provider import get_llm_provider
from app.models.schemas import JobStatus

logger = get_logger(__name__)

SYSTEM_PROMPT = """Bạn là AI chuyên phân tích báo cáo kinh tế vĩ mô Việt Nam từ NHNN và NSO.
Nhiệm vụ: tóm tắt số liệu đã thu thập, nêu rõ nguồn, không bịa số.
Trả lời bằng tiếng Việt, cuối cùng có JSON:
{
  "status": "success" | "partial" | "failed",
  "summary": "...",
  "indicators": {},
  "sources": [],
  "notes": "..."
}
"""


class AgentOrchestrator:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm = get_llm_provider()
        self.source_tool = OfficialSourceTool()
        self.pdf_extractor = PDFExtractor()
        self.excel_extractor = ExcelExtractor()
        self.jobs: Dict[str, Dict[str, Any]] = {}

    def create_job(self, query: str) -> str:
        job_id = str(uuid.uuid4())
        now = datetime.utcnow()
        self.jobs[job_id] = {
            "job_id": job_id,
            "query": query,
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

    def run(self, query: str, job_id: Optional[str] = None) -> Dict[str, Any]:
        if job_id is None:
            job_id = self.create_job(query)
        job = self.jobs[job_id]
        job["status"] = JobStatus.RUNNING
        job["updated_at"] = datetime.utcnow()
        job["message"] = "Agent is running"

        try:
            result = self._execute(query, job)
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

    def _execute(self, query: str, job: Dict[str, Any]) -> Dict[str, Any]:
        steps: List[Dict[str, Any]] = []

        # 1) Always collect official bundle (reliable path)
        logger.info("collect_macro_bundle_start")
        bundle = self.source_tool.collect_macro_bundle()
        steps.append(
            {
                "step": "collect_macro_bundle",
                "nso_reports": len(bundle.get("nso_report_list") or []),
                "nhnn_reports": len(bundle.get("nhnn_report_list") or []),
                "fx_status": (bundle.get("exchange_rate") or {}).get("status"),
                "nso_status": (bundle.get("nso_latest") or {}).get("status"),
            }
        )

        # 2) Try download first PDF from NHNN list if any
        collected_files: List[Dict[str, Any]] = []
        for r in (bundle.get("nhnn_report_list") or [])[:3]:
            u = r.get("url") or ""
            if ".pdf" in u.lower():
                dl = self.source_tool.download_file(u, "nhnn")
                steps.append({"step": "download_nhnn_pdf", "result": {k: v for k, v in dl.items() if k != "content"}})
                if dl.get("status") == "ok":
                    collected_files.append(dl)
                    try:
                        extracted = self.pdf_extractor.extract(dl["local_path"])
                        inds = self.pdf_extractor.extract_key_indicators(extracted.get("text", ""))
                        dl["indicators"] = inds
                        # save tables
                        for i, t in enumerate(extracted.get("tables", [])[:3]):
                            df = t.get("dataframe")
                            if df is not None and not df.empty:
                                csv_path = (
                                    self.settings.processed_dir
                                    / "macro"
                                    / f"{Path(dl['local_path']).stem}_t{i}.csv"
                                )
                                csv_path.parent.mkdir(parents=True, exist_ok=True)
                                df.to_csv(csv_path, index=False, encoding="utf-8-sig")
                    except Exception as e:
                        dl["extract_error"] = str(e)
                break

        # 3) Merge indicators
        indicators: Dict[str, Any] = {}
        fx = bundle.get("exchange_rate") or {}
        if fx.get("rates"):
            indicators["exchange_rate"] = fx["rates"]
        nso = bundle.get("nso_latest") or {}
        if nso.get("indicators"):
            indicators["nso"] = nso["indicators"]
        for f in collected_files:
            if f.get("indicators"):
                indicators["pdf"] = f["indicators"]

        # 4) LLM summary
        payload_for_llm = {
            "user_query": query,
            "exchange_rate": fx.get("rates"),
            "exchange_source": fx.get("source"),
            "nso_report": {
                "title": nso.get("title") or (nso.get("report") or {}).get("title"),
                "url": nso.get("url"),
                "indicators": nso.get("indicators"),
                "preview": (nso.get("text_preview") or "")[:2500],
            },
            "nso_list": bundle.get("nso_report_list"),
            "nhnn_list": bundle.get("nhnn_report_list"),
            "files": [
                {"url": f.get("url"), "path": f.get("local_path"), "indicators": f.get("indicators")}
                for f in collected_files
            ],
        }

        summary_prompt = f"""Yêu cầu người dùng: {query}

Dữ liệu đã thu thập từ nguồn chính thức (JSON):
{json.dumps(payload_for_llm, ensure_ascii=False, default=str)[:12000]}

Hãy:
1. Tóm tắt số liệu liên quan yêu cầu (tỷ giá, GDP, CPI, tín dụng, XNK nếu có).
2. Nêu rõ nguồn URL.
3. Nếu thiếu số liệu, nói rõ còn thiếu gì — không bịa.
4. Trả JSON cuối cùng theo format đã nêu.
"""
        final_raw = self.llm.chat(SYSTEM_PROMPT, summary_prompt)
        final = self._safe_json(final_raw)
        if not final:
            final = {
                "status": "partial" if indicators else "failed",
                "summary": final_raw[:1500],
                "indicators": indicators,
                "sources": [
                    fx.get("source"),
                    nso.get("url"),
                ],
                "notes": "LLM JSON parse failed; raw summary returned",
                "raw_data": payload_for_llm,
            }
        else:
            # Ensure indicators/sources present
            if not final.get("indicators"):
                final["indicators"] = indicators
            final.setdefault("raw_data", {
                "exchange_rate": fx.get("rates"),
                "nso_indicators": nso.get("indicators"),
                "nso_url": nso.get("url"),
                "files": collected_files,
            })

        job["steps"] = steps
        return final

    @staticmethod
    def _safe_json(text: str) -> Optional[Dict]:
        text = (text or "").strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        try:
            return json.loads(text)
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except Exception:
                    return None
            return None
