# Vietnam Macro AI Agent

API FastAPI: thu thập báo cáo kinh tế vĩ mô Việt Nam (NHNN + NSO) và **BCTC công ty theo mã chứng khoán**, extract PDF/Excel, phân tích.

**LLM:** Groq (primary) + auto-switch fallback khi rate-limit.

## Tính năng

- Gõ tự do câu hỏi về báo cáo vĩ mô (NSO, NHNN, tỷ giá, CPI, GDP, tín dụng…)
- Nhập **mã chứng khoán** (VNM, HPG, FPT…) → hệ thống lấy BCTC từ CafeF / Vietstock
- Download PDF, extract text/tables, tóm tắt bằng LLM

## Deploy Render

1. Push repo lên GitHub
2. Render → New → Blueprint → chọn repo (đọc `render.yaml`)
3. Set env: `GROQ_API_KEY=gsk_...`
4. Deploy

## API

**Chạy đồng bộ:**
```
POST /api/v1/agent/run/sync
{
  "query": "Lấy báo cáo NSO và NHNN mới nhất",
  "ticker": "VNM"   // optional
}
```

**Chạy nền:**
```
POST /api/v1/agent/run
→ job_id
GET /api/v1/agent/jobs/{job_id}
```

- Health: `GET /api/v1/health`
- Docs: `/docs`
- UI: `/`

## Cấu trúc

```
app/
  agent/          # orchestrator + tools (SBV, NSO, company)
  api/v1/         # routes
  extractors/     # PDF + Excel
  llm/            # Groq provider + fallback
  models/         # pydantic schemas
  templates/ui.html
data/raw/{nhnn,nso,companies,other}
```
