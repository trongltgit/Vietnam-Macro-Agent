"""Financial ratio engine – bank-grade calculations."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.models.schemas import FinancialRatios, FinancialStatement


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return round(a / b, 4)


def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """(a/b - 1) * 100"""
    r = _safe_div(a, b)
    if r is None:
        return None
    return round((r - 1) * 100, 2)


def compute_ratios(
    current: FinancialStatement,
    prior: Optional[FinancialStatement] = None,
) -> FinancialRatios:
    """Compute standard ratios from one (or two) periods."""
    r = FinancialRatios()

    # Profitability
    r.roe = _safe_div(current.net_profit, current.total_equity)
    r.roa = _safe_div(current.net_profit, current.total_assets)
    r.gross_margin = _safe_div(current.gross_profit, current.revenue)
    r.ebit_margin = _safe_div(current.ebit or current.operating_profit, current.revenue)
    r.net_margin = _safe_div(current.net_profit, current.revenue)

    # Leverage
    r.debt_to_equity = _safe_div(current.total_debt, current.total_equity)
    r.debt_to_assets = _safe_div(current.total_debt, current.total_assets)

    # Liquidity
    r.current_ratio = _safe_div(current.current_assets, current.current_liabilities)
    r.quick_ratio = _safe_div(
        (current.current_assets or 0) - 0,  # inventory not always available
        current.current_liabilities,
    )
    r.cash_ratio = _safe_div(current.cash, current.current_liabilities)

    # Efficiency
    r.asset_turnover = _safe_div(current.revenue, current.total_assets)

    # Growth
    if prior:
        r.revenue_growth = _pct(current.revenue, prior.revenue)
        r.profit_growth = _pct(current.net_profit, prior.net_profit)

    # Per share (if provided externally)
    # eps / bvps / pe / pb left for caller if market data available

    return r


def ratios_to_dict(r: FinancialRatios) -> Dict[str, Any]:
    return {k: v for k, v in r.model_dump().items() if v is not None}


def ratios_from_key_figures(figs: Dict[str, Any]) -> FinancialRatios:
    """Best-effort parse from scraped key_figures (string numbers)."""
    def f(key: str) -> Optional[float]:
        v = figs.get(key)
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).replace(",", "").replace("%", "").strip()
        try:
            return float(s)
        except ValueError:
            return None

    return FinancialRatios(
        roe=f("roe"),
        roa=f("roa"),
        eps=f("eps"),
        pe=f("pe"),
        pb=f("pb"),
        net_margin=None,
        revenue_growth=None,
    )
