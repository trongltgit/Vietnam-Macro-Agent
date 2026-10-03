"""
Agent orchestrator using LLM + tools (ReAct style, controlled).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.tools.official_sources import OfficialSourceTool
from app.core.config import get_settings
from app.core.logging import get_logger
from app.extractors.excel_extractor import ExcelExtractor
from app.extractors.pdf_extractor import PDFExtractor
from app.llm.provider import get_llm_provider
from app.models.schemas import JobStatus

logger = get_logger(__name__)

SYSTEM_PROMPT = """Bạn là AI Agent chuyên thu thập và phân tích báo cáo kinh tế vĩ mô Việt Nam từ nguồn chính thức (NHNN - Ngân hàng Nhà nước, NSO - Cục Thống kê).

Nhiệm vụ:
1. Hiểu yêu cầu người dùng (lấy báo cáo gì, năm nào, chủ đề gì).
2. Sử dụng các tool có sẵn để tìm link chính thức, tải file PDF/Excel.
3. Extract số liệu quan trọng (GDP, CPI, tỷ giá, XNK, tín dụng...).
4. Trả về kết quả có cấu trúc JSON rõ ràng.

Quy tắc bắt buộc:
- CHỈ dùng nguồn chính thức NHNN (sbv.gov.vn) và NSO (nso.gov.vn).
- Không bịa link hoặc số liệu.
- Nếu không tìm thấy, nói rõ.
- Ưu tiên file PDF/Excel mới nhất.
- Trả lời cuối cùng phải là JSON hợp lệ với các key: status, summary, files, indicators, notes.
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
        collected_files: List[Dict[str, Any]] = []
        indicators: Dict[str, Any] = {}

        # Step 1: Plan with LLM
        plan_prompt = f"""Yêu cầu người dùng: {query}

Các tool bạn có:
1. list_nso_reports - liệt kê báo cáo NSO mới
2. list_nhnn_reports - liệt kê báo cáo NHNN
3. fetch_page(url) - lấy nội dung trang
4. download_file(url, subdir) - tải file
5. extract_pdf(path) - extract text + tables từ PDF

Hãy trả về kế hoạch ngắn gọn dạng JSON:
{{
  "actions": [
    {{"tool": "list_nso_reports", "reason": "..."}},
    {{"tool": "download_file", "url": "...", "subdir": "nso"}},
    ...
  ],
  "expected_indicators": ["gdp_growth", "cpi", ...]
}}
Chỉ trả JSON, không giải thích thêm."""

        plan_raw = self.llm.chat(SYSTEM_PROMPT, plan_prompt)
        steps.append({"step": "plan", "raw": plan_raw[:2000]})

        # Parse plan (best effort)
        plan = self._safe_json(plan_raw)
        actions = plan.get("actions", []) if isinstance(plan, dict) else []

        # Step 2: Execute tools based on plan + fallback heuristics
        if not actions:
            # Fallback heuristic
            actions = [
                {"tool": "list_nso_reports"},
                {"tool": "list_nhnn_reports"},
            ]

        for action in actions[:6]:  # limit steps
            tool = action.get("tool")
            try:
                if tool == "list_nso_reports":
                    reports = self.source_tool.list_nso_latest_reports()
                    steps.append({"tool": tool, "result_count": len(reports), "sample": reports[:3]})
                    # Auto download first PDF-like if present
                    for r in reports:
                        if r.get("type") in [".pdf", "pdf"] or ".pdf" in (r.get("url") or "").lower():
                            dl = self.source_tool.download_file(r["url"], "nso")
                            if dl.get("status") == "ok":
                                collected_files.append(dl)
                                break

                elif tool == "list_nhnn_reports":
                    reports = self.source_tool.list_nhnn_reports()
                    steps.append({"tool": tool, "result_count": len(reports), "sample": reports[:3]})
                    for r in reports:
                        if r.get("type") in [".pdf", "pdf"] or ".pdf" in (r.get("url") or "").lower():
                            dl = self.source_tool.download_file(r["url"], "nhnn")
                            if dl.get("status") == "ok":
                                collected_files.append(dl)
                                break

                elif tool == "fetch_page":
                    url = action.get("url")
                    if url:
                        page = self.source_tool.fetch_page(url)
                        steps.append({"tool": tool, "url": url, "title": page.get("title")})
                        # Look for PDF links
                        for link in page.get("links", []):
                            if link.get("type") in [".pdf", ".xlsx"]:
                                dl = self.source_tool.download_file(link["url"], "other")
                                if dl.get("status") == "ok":
                                    collected_files.append(dl)

                elif tool == "download_file":
                    url = action.get("url")
                    subdir = action.get("subdir", "other")
                    if url:
                        dl = self.source_tool.download_file(url, subdir)
                        steps.append({"tool": tool, "result": dl})
                        if dl.get("status") == "ok":
                            collected_files.append(dl)

                elif tool == "extract_pdf":
                    path = action.get("path")
                    if path:
                        extracted = self.pdf_extractor.extract(path)
                        steps.append({
                            "tool": tool,
                            "path": path,
                            "tables": len(extracted.get("tables", [])),
                            "text_chars": len(extracted.get("text", "")),
                        })
                        # Heuristic indicators
                        inds = self.pdf_extractor.extract_key_indicators(extracted.get("text", ""))
                        indicators.update(inds)
            except Exception as e:
                steps.append({"tool": tool, "error": str(e)})
                logger.warning("tool_execution_failed", tool=tool, error=str(e))

        # Step 3: Extract all collected PDFs
        for f in collected_files:
            path = f.get("local_path")
            if path and path.lower().endswith(".pdf"):
                try:
                    extracted = self.pdf_extractor.extract(path)
                    f["extracted"] = {
                        "tables_count": len(extracted.get("tables", [])),
                        "text_chars": len(extracted.get("text", "")),
                        "indicators": self.pdf_extractor.extract_key_indicators(
                            extracted.get("text", "")
                        ),
                    }
                    indicators.update(f["extracted"]["indicators"])
                    # Save tables as CSV
                    for i, t in enumerate(extracted.get("tables", [])[:5]):
                        df = t.get("dataframe")
                        if df is not None and not df.empty:
                            csv_path = (
                                self.settings.processed_dir
                                / "macro"
                                / f"{Path(path).stem}_table_{i}.csv"
                            )
                            csv_path.parent.mkdir(parents=True, exist_ok=True)
                            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
                            f.setdefault("csv_tables", []).append(str(csv_path))
                except Exception as e:
                    f["extract_error"] = str(e)

        # Step 4: Final summary with LLM
        summary_prompt = f"""Yêu cầu gốc: {query}

Kết quả thu thập:
- Files: {json.dumps([{k: v for k, v in f.items() if k != 'extracted'} for f in collected_files], ensure_ascii=False, default=str)[:3000]}
- Indicators tìm được: {json.dumps(indicators, ensure_ascii=False)}

Hãy viết summary ngắn + JSON cuối cùng:
{{
  "status": "success" | "partial" | "failed",
  "summary": "mô tả ngắn bằng tiếng Việt",
  "files": [...],
  "indicators": {{...}},
  "notes": "..."
}}
"""
        final_raw = self.llm.chat(SYSTEM_PROMPT, summary_prompt)
        final = self._safe_json(final_raw) or {
            "status": "partial" if collected_files else "failed",
            "summary": final_raw[:500],
            "files": collected_files,
            "indicators": indicators,
            "notes": "LLM summary parse failed, raw returned",
        }

        job["steps"] = steps
        return final

    @staticmethod
    def _safe_json(text: str) -> Optional[Dict]:
        text = text.strip()
        # Try extract JSON block
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        try:
            return json.loads(text)
        except Exception:
            # Try find first { ... }
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except Exception:
                    return None
            return None
