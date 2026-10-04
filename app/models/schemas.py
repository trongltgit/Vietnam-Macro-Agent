"""
Pydantic schemas for API request / response.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class ReportSource(str, Enum):
    NHNN = "nhnn"
    NSO = "nso"
    COMPANY = "company"
    OTHER = "other"


class FetchRequest(BaseModel):
    sources: List[ReportSource] = Field(
        default=[ReportSource.NHNN, ReportSource.NSO],
        description="Sources to fetch from",
    )
    topics: List[str] = Field(
        default=["macro", "exchange_rate", "trade", "monetary"],
        description="Topics of interest",
    )
    year: Optional[int] = Field(default=None)
    force_refresh: bool = Field(default=False)


class ExtractRequest(BaseModel):
    file_path: str
    extract_tables: bool = True
    extract_text: bool = True


class AnalysisRequest(BaseModel):
    variables: Optional[List[str]] = Field(default=None)
    method: str = Field(default="pearson")
    min_periods: int = Field(default=3)


class MergeToExcelRequest(BaseModel):
    sheet_name: str = Field(default="Macro_External")
    overwrite_sheet: bool = Field(default=False)


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str
    created_at: datetime
    updated_at: datetime
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    llm_status: Dict[str, Any]
    timestamp: datetime


class ReportMetadata(BaseModel):
    source: ReportSource
    title: str
    url: Optional[str] = None
    local_path: Optional[str] = None
    published_date: Optional[str] = None
    file_type: str
    extracted_at: Optional[datetime] = None
    tables_count: int = 0
    text_chars: int = 0


class AgentRunRequest(BaseModel):
    """Natural language request + optional stock ticker."""
    query: str = Field(
        ...,
        examples=[
            "Lấy báo cáo kinh tế - xã hội mới nhất của NSO và tỷ giá trung tâm NHNN",
            "Tải Annual Report NHNN 2024",
            "Lấy BCTC mới nhất của VNM",
        ],
    )
    ticker: Optional[str] = Field(
        default=None,
        description="Mã chứng khoán (VD: VNM, HPG, FPT). Nếu có, hệ thống sẽ lấy BCTC công ty.",
        examples=["VNM", "HPG", "FPT"],
    )
    max_iterations: Optional[int] = None
