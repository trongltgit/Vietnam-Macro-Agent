from fastapi import APIRouter, HTTPException

from app.analysis.correlation import CorrelationAnalyzer
from app.models.schemas import AnalysisRequest, MergeToExcelRequest
from app.pipeline.merge_excel import ExcelMergePipeline

router = APIRouter(prefix="/analysis", tags=["Analysis"])


@router.post("/correlation")
async def run_correlation(request: AnalysisRequest):
    """
    Chạy phân tích correlation trên Excel phase-1 + dữ liệu processed.
    """
    analyzer = CorrelationAnalyzer()
    try:
        result = analyzer.run_full_analysis(
            method=request.method,
            variables=request.variables,
            min_periods=request.min_periods,
        )
        return {"status": "ok", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/merge-to-excel")
async def merge_to_excel(request: MergeToExcelRequest):
    """
    Merge toàn bộ dữ liệu processed vào file Excel phase-1.
    Sheets mới sẽ có prefix Ext_ để không ghi đè dữ liệu internal.
    """
    pipeline = ExcelMergePipeline()
    try:
        result = pipeline.merge()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
