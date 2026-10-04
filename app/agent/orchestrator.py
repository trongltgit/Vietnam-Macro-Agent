"""
Agent orchestrator:
1) Thu thập số liệu NHNN/NSO + BCTC công ty (nếu có mã CK)
2) Viết BÁO CÁO TỔNG HỢP chuyên nghiệp (không dump link)
3) Xuất file CSV + text báo cáo để user nạp vào Excel phase 1
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

SYSTEM_PROMPT = """Bạn là chuyên gia phân tích kinh tế vĩ mô và doanh nghiệp Việt Nam.
Nhiệm vụ: viết BÁO CÁO TỔNG HỢP chuyên nghiệp bằng tiếng Việt dựa trên số liệu đã thu thập.

CẤU TRÚC BẮT BUỘC của báo cáo (markdown):

# BÁO CÁO TỔNG HỢP KINH TẾ VĨ MÔ & DOANH NGHIỆP
## 1. Vĩ mô thế giới (bối cảnh)
## 2. Vĩ mô Việt Nam (GDP, CPI, tín dụng, XNK, tỷ giá — chỉ dùng số đã có)
## 3. Các ngành chính (ngắn gọn, gắn với số liệu VN nếu có)
## 4. Doanh nghiệp (nếu có mã CK / BCTC)
## 5. Kết luận & điểm cần theo dõi

QUY TẮC:
- Viết thành đoạn văn phân tích, KHÔNG liệt kê URL.
- Chỉ dùng số liệu có trong dữ liệu đầu vào; thiếu thì nói rõ "chưa có số liệu".
- Không bịa số.
- Cuối cùng (sau báo cáo) thêm một khối JSON:
```json
{"status":"success|partial|failed","indicators":{},"notes":"..."}
```
"""


def _extract_ticker(query: str) -> Optional[str]:
    q = query.upper()
    m = re.search(r"(?:MÃ|MA|TICKER|CỔ PHIẾU|CO PHIEU|STOCK)\s*[:=]?\s*([A-Z0-9]{3,10})", q)
    if m:
        return m.group(1)
    m2 = re.search(r"\b([A-Z]{3,4})\b", q)
    if m2:
        cand = m2.group(1)
        stop = {
            "NSO", "NHNN", "SBV", "GSO", "GDP", "CPI", "USD", "VND",
            "PDF", "API", "URL", "HTTP", "HTML", "JSON", "LLM", "THE", "AND",
            "CSV", "XLS", "BCTC",
        }
        if cand not in stop:
            return cand
    return None


class AgentOrchestrator:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm = get_llm_provider()
        self.source_tool = OfficialSourceTool()
        self.pdf_extractor = PDFExtractor()
        self.jobs: Dict[str, Dict[str, Any]] = {}

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

        # 1) Macro bundle
        bundle = self.source_tool.collect_macro_bundle()
        steps.append({
            "step": "collect_macro",
            "fx": (bundle.get("exchange_rate") or {}).get("status"),
            "nso": (bundle.get("nso_latest") or {}).get("status"),
        })

        # 2) Optional NHNN PDF download + extract
        collected_files: List[Dict[str, Any]] = []
        for r in (bundle.get("nhnn_report_list") or [])[:2]:
            u = r.get("url") or ""
            if ".pdf" in u.lower():
                dl = self.source_tool.download_file(u, "nhnn")
                if dl.get("status") == "ok":
                    collected_files.append(dl)
                    try:
                        extracted = self.pdf_extractor.extract(dl["local_path"])
                        dl["indicators"] = self.pdf_extractor.extract_key_indicators(
                            extracted.get("text", "")
                        )
                        dl["text_preview"] = (extracted.get("text") or "")[:2000]
                    except Exception as e:
                        dl["extract_error"] = str(e)
                break

        # 3) Company
        company_data: Optional[Dict[str, Any]] = None
        if ticker:
            company_data = self.source_tool.fetch_company_reports(ticker)
            steps.append({
                "step": "company",
                "ticker": ticker,
                "status": company_data.get("status"),
                "reports": len(company_data.get("reports") or []),
            })
            for rep in (company_data.get("reports") or [])[:2]:
                url = rep.get("url") or ""
                if ".pdf" in url.lower():
                    dl = self.source_tool.download_file(url, "companies")
                    if dl.get("status") == "ok":
                        collected_files.append(dl)
                        try:
                            extracted = self.pdf_extractor.extract(dl["local_path"])
                            dl["text_preview"] = (extracted.get("text") or "")[:2000]
                            inds = self.pdf_extractor.extract_key_indicators(
                                extracted.get("text", "")
                            )
                            if inds and company_data is not None:
                                company_data.setdefault("key_figures", {}).update(inds)
                        except Exception as e:
                            dl["extract_error"] = str(e)

        fx = bundle.get("exchange_rate") or {}
        nso = bundle.get("nso_latest") or {}
        indicators: Dict[str, Any] = {}
        if fx.get("rates"):
            indicators["exchange_rate_usd_vnd"] = fx["rates"].get("usd_vnd_central")
        if nso.get("indicators"):
            indicators.update(nso["indicators"])
        if company_data and company_data.get("key_figures"):
            indicators["company_ticker"] = ticker
            indicators["company_name"] = company_data.get("company_name")
            for k, v in company_data["key_figures"].items():
                indicators[f"company_{k}"] = v

        payload = {
            "query": query,
            "ticker": ticker,
            "exchange_rate": fx,
            "nso": {
                "status": nso.get("status"),
                "url": nso.get("url"),
                "indicators": nso.get("indicators"),
                "preview": (nso.get("text_preview") or "")[:3000],
            },
            "company": {
                "ticker": ticker,
                "name": (company_data or {}).get("company_name"),
                "key_figures": (company_data or {}).get("key_figures"),
                "status": (company_data or {}).get("status"),
            } if ticker else None,
            "file_previews": [
                {"path": f.get("local_path"), "indicators": f.get("indicators"),
                 "preview": (f.get("text_preview") or "")[:800]}
                for f in collected_files
            ],
        }

        user_prompt = f"""Yêu cầu: {query}
{"Mã CK: " + ticker if ticker else ""}

Số liệu đã thu thập (JSON):
{json.dumps(payload, ensure_ascii=False, default=str)[:14000]}

Hãy viết BÁO CÁO TỔNG HỢP theo đúng cấu trúc trong system prompt.
Không liệt kê URL trong phần báo cáo. Số liệu thiếu thì nói rõ.
"""
        raw = self.llm.chat(SYSTEM_PROMPT, user_prompt)

        # Split narrative report vs trailing JSON
        report_md, meta = self._split_report_and_json(raw)
        if not meta:
            meta = {
                "status": "partial" if indicators else "failed",
                "indicators": indicators,
                "notes": "Không parse được JSON meta từ LLM",
            }
        else:
            if not meta.get("indicators"):
                meta["indicators"] = indicators
            meta.setdefault("status", "partial" if indicators else "success")

        # Export files for user to load into their Excel
        export_info = self._export_files(job["job_id"], report_md, meta.get("indicators") or indicators, ticker)

        result = {
            "status": meta.get("status", "partial"),
            "report": report_md,  # full narrative — main deliverable
            "summary": report_md[:500] + ("…" if len(report_md) > 500 else ""),
            "indicators": meta.get("indicators") or indicators,
            "notes": meta.get("notes", ""),
            "exports": export_info,  # paths to CSV / MD files
            "sources_used": {
                "nso": nso.get("url"),
                "fx": fx.get("source"),
                "company_pages": (company_data or {}).get("sources"),
            },
        }
        job["steps"] = steps
        return result

    def _export_files(
        self,
        job_id: str,
        report_md: str,
        indicators: Dict[str, Any],
        ticker: Optional[str],
    ) -> Dict[str, Any]:
        """Write report.md + indicators.csv into data/processed/reports/ for download."""
        out_dir = self.settings.processed_dir / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        base = f"{stamp}_{job_id[:8]}"
        if ticker:
            base += f"_{ticker}"

        md_path = out_dir / f"{base}_baocao.md"
        csv_path = out_dir / f"{base}_chisieu.csv"
        xlsx_path = out_dir / f"{base}_chisieu.xlsx"

        md_path.write_text(report_md or "", encoding="utf-8")

        # Flatten indicators to 2-col table
        rows = []
        for k, v in (indicators or {}).items():
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            rows.append({"Chi_tieu": k, "Gia_tri": v, "Ticker": ticker or "", "Job": job_id})
        df = pd.DataFrame(rows) if rows else pd.DataFrame(
            {"Chi_tieu": ["(trống)"], "Gia_tri": [""], "Ticker": [ticker or ""], "Job": [job_id]}
        )
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        try:
            df.to_excel(xlsx_path, index=False)
        except Exception:
            xlsx_path = None

        info = {
            "report_md": str(md_path),
            "indicators_csv": str(csv_path),
            "indicators_xlsx": str(xlsx_path) if xlsx_path and xlsx_path.exists() else None,
            "download_hints": [
                f"/api/v1/reports/download-processed/reports/{md_path.name}",
                f"/api/v1/reports/download-processed/reports/{csv_path.name}",
            ],
        }
        if xlsx_path and Path(xlsx_path).exists():
            info["download_hints"].append(
                f"/api/v1/reports/download-processed/reports/{Path(xlsx_path).name}"
            )
        return info

    @staticmethod
    def _split_report_and_json(text: str) -> tuple:
        text = (text or "").strip()
        meta = None
        report = text
        # Try extract last JSON block
        if "```json" in text:
            parts = text.split("```json")
            report = parts[0].strip()
            try:
                meta = json.loads(parts[-1].split("```")[0].strip())
            except Exception:
                pass
        else:
            start = text.rfind("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    meta = json.loads(text[start : end + 1])
                    report = text[:start].strip()
                except Exception:
                    pass
        return report, meta
