"""Pydantic schemas – professional research platform."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class ResearchDepth(str, Enum):
    QUICK = "quick"          # 1-2 pages summary
    STANDARD = "standard"    # Full research note ~8-12 pages
    DEEP = "deep"            # Deep dive + valuation / credit assessment


class CompanyIdentifier(BaseModel):
    """Identify any company operating in Vietnam (listed or not)."""
    name: Optional[str] = Field(None, description="Tên công ty (VD: Công ty TNHH ABC, Vinamilk)")
    ticker: Optional[str] = Field(None, description="Mã CK nếu có (VNM, HPG...)")
    tax_code: Optional[str] = Field(None, description="Mã số thuế (MST)")
    address: Optional[str] = None
    industry: Optional[str] = None


class ResearchRequest(BaseModel):
    query: str = Field(
        ...,
        description="Câu hỏi / yêu cầu phân tích bằng ngôn ngữ tự nhiên",
        examples=[
            "Phân tích sâu công ty Vinamilk năm 2024-2025",
            "Báo cáo vĩ mô Việt Nam Q3/2025 và tác động đến ngành ngân hàng",
            "Đánh giá tín dụng Công ty TNHH XYZ (MST 0123456789)",
        ],
    )
    company: Optional[CompanyIdentifier] = None
    depth: ResearchDepth = ResearchDepth.STANDARD
    include_macro: bool = True
    include_peers: bool = True
    include_valuation: bool = True
    language: str = "vi"
    export_pdf: bool = True
    export_excel: bool = True


class FinancialRatios(BaseModel):
    """Key financial ratios – bank-grade."""
    # Profitability
    roe: Optional[float] = None
    roa: Optional[float] = None
    gross_margin: Optional[float] = None
    ebit_margin: Optional[float] = None
    net_margin: Optional[float] = None
    # Leverage & Solvency
    debt_to_equity: Optional[float] = None
    debt_to_assets: Optional[float] = None
    interest_coverage: Optional[float] = None
    # Liquidity
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    cash_ratio: Optional[float] = None
    # Efficiency
    asset_turnover: Optional[float] = None
    inventory_turnover: Optional[float] = None
    receivables_days: Optional[float] = None
    # Growth (YoY %)
    revenue_growth: Optional[float] = None
    profit_growth: Optional[float] = None
    # Per share
    eps: Optional[float] = None
    bvps: Optional[float] = None
    # Valuation (if listed)
    pe: Optional[float] = None
    pb: Optional[float] = None
    ev_ebitda: Optional[float] = None
    dividend_yield: Optional[float] = None


class CompanyProfile(BaseModel):
    name: str
    ticker: Optional[str] = None
    tax_code: Optional[str] = None
    legal_form: Optional[str] = None  # CTCP, TNHH, Tập đoàn...
    industry: Optional[str] = None
    sector: Optional[str] = None
    founded_year: Optional[int] = None
    headquarters: Optional[str] = None
    website: Optional[str] = None
    employees: Optional[int] = None
    description: Optional[str] = None
    major_shareholders: List[Dict[str, Any]] = Field(default_factory=list)
    management: List[Dict[str, Any]] = Field(default_factory=list)
    listing_status: str = "unlisted"  # listed | unlisted | delisted
    exchange: Optional[str] = None  # HOSE | HNX | UPCOM


class MacroSnapshot(BaseModel):
    as_of: Optional[str] = None
    gdp_growth: Optional[float] = None
    cpi_yoy: Optional[float] = None
    credit_growth: Optional[float] = None
    usd_vnd: Optional[float] = None
    policy_rate: Optional[float] = None
    trade_balance: Optional[float] = None
    fdi_disbursed: Optional[float] = None
    notes: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)


class FinancialStatement(BaseModel):
    period: str  # 2024, 2024Q3, TTM...
    revenue: Optional[float] = None
    cogs: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_profit: Optional[float] = None
    ebit: Optional[float] = None
    ebitda: Optional[float] = None
    net_profit: Optional[float] = None
    total_assets: Optional[float] = None
    total_equity: Optional[float] = None
    total_debt: Optional[float] = None
    cash: Optional[float] = None
    current_assets: Optional[float] = None
    current_liabilities: Optional[float] = None
    operating_cashflow: Optional[float] = None
    capex: Optional[float] = None
    free_cashflow: Optional[float] = None
    unit: str = "VND billion"


class ResearchReport(BaseModel):
    """Full research output structure."""
    report_id: str
    title: str
    generated_at: datetime
    depth: ResearchDepth
    query: str
    company: Optional[CompanyProfile] = None
    macro: Optional[MacroSnapshot] = None
    financials: List[FinancialStatement] = Field(default_factory=list)
    ratios: Optional[FinancialRatios] = None
    peers: List[Dict[str, Any]] = Field(default_factory=list)
    executive_summary: str = ""
    business_overview: str = ""
    financial_analysis: str = ""
    industry_macro_linkage: str = ""
    valuation_or_credit: str = ""
    risks: str = ""
    outlook_recommendation: str = ""
    appendix_notes: str = ""
    sources: List[str] = Field(default_factory=list)
    confidence: str = "medium"  # high | medium | low
    pdf_path: Optional[str] = None
    excel_path: Optional[str] = None
    markdown_path: Optional[str] = None


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str
    created_at: datetime
    updated_at: datetime
    progress: List[str] = Field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    llm_status: Dict[str, Any]
    timestamp: datetime
