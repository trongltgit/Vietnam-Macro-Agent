# Vietnam Macro AI Agent

API FastAPI production: thu thập báo cáo kinh tế vĩ mô Việt Nam (NHNN + NSO), extract PDF/Excel, nạp vào Excel phase 1, phân tích correlation.

**LLM:** Groq (primary) + auto-switch fallback khi rate-limit.

## Deploy thẳng lên Render (không cần chạy local)

### 1. Tạo repo GitHub

Trên máy bạn (hoặc GitHub web):

```bash
# Nếu chưa có git
cd vietnam-macro-agent
git init
git add .
git commit -m "Vietnam Macro AI Agent - production FastAPI + Groq"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/vietnam-macro-agent.git
git push -u origin main
```

Hoặc tạo repo trống trên GitHub → Upload folder `vietnam-macro-agent`.

### 2. Deploy Render

1. Vào https://dashboard.render.com → đăng nhập
2. **New** → **Blueprint**
3. Connect GitHub → chọn repo `vietnam-macro-agent`
4. Render đọc `render.yaml` tự động
5. Điền biến môi trường bắt buộc:
   - `GROQ_API_KEY` = `gsk_...` (key Groq của bạn)
6. **Apply** → chờ build + deploy (5–10 phút lần đầu)

### 3. Sau khi live

- Health: `https://vietnam-macro-agent-xxxx.onrender.com/api/v1/health`
- Docs (Swagger): `https://vietnam-macro-agent-xxxx.onrender.com/docs`
- Root: `https://vietnam-macro-agent-xxxx.onrender.com/`

### 4. Dùng API online

**Chạy agent (đồng bộ):**
```
POST /api/v1/agent/run/sync
Body: {"query": "Lấy báo cáo kinh tế xã hội mới nhất NSO và báo cáo NHNN"}
```

**Chạy agent nền:**
```
POST /api/v1/agent/run
→ nhận job_id
GET /api/v1/agent/jobs/{job_id}
```

**Danh sách file đã tải:** `GET /api/v1/reports/list`

**Merge vào Excel phase 1:** `POST /api/v1/analysis/merge-to-excel`

**Correlation:** `POST /api/v1/analysis/correlation`

## Cấu trúc chính

```
app/
  main.py              # FastAPI entry
  llm/provider.py      # Groq + circuit breaker + fallback
  agent/orchestrator.py
  agent/tools/official_sources.py   # NHNN + NSO
  extractors/          # PDF + Excel
  pipeline/            # merge Excel
  analysis/            # correlation
  api/v1/              # endpoints
```

## Lưu ý Render free

- Service ngủ sau ~15 phút không request → request đầu tiên có thể chậm 30–60s (cold start).
- Disk 1GB gắn `/app/data` → file PDF/CSV/Excel được giữ giữa các lần deploy.
- Rate limit Groq free: agent đã có auto-switch model + retry.

## File Excel phase 1

Upload sau khi deploy bằng API (hoặc mount disk). Sheets external sẽ có prefix `Ext_` để không ghi đè dữ liệu internal của bạn.
