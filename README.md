# Vietnam Research Agent v2

**Nền tảng phân tích vĩ mô & doanh nghiệp Việt Nam chuyên sâu**  
Chuẩn research note ngân hàng thương mại / báo cáo chính phủ / đánh giá tập đoàn lớn.

---

## Điểm khác biệt so với bản cũ

| Hạng mục | Bản cũ | **Bản mới (v2)** |
|----------|--------|------------------|
| Đối tượng | Chỉ mã CK niêm yết | **Mọi công ty** (tên / MST / ticker) |
| Phân tích | Template cứng, nông | **Multi-section LLM** chuẩn research note |
| Cấu trúc báo cáo | 5 mục chung chung | **8 mục chuyên sâu** (Exec Summary → Risks → Outlook) |
| Xuất file | TXT + CSV | **PDF chuyên nghiệp** + Markdown + Excel |
| Chỉ số tài chính | Regex thô | Engine tính ROE/ROA/margin/leverage/liquidity |
| Độ sâu | Một mức | Quick / Standard / Deep |
| Văn phong | Nghèo nàn | Giọng Senior Research Analyst (CFA-style) |

---

## Cấu trúc báo cáo (chuẩn NHTM)

1. **Tóm tắt Điều hành** (Executive Summary)  
2. **Tổng quan Doanh nghiệp & Mô hình Kinh doanh**  
3. **Phân tích Tài chính** (profitability, leverage, liquidity, growth)  
4. **Liên kết Vĩ mô – Ngành**  
5. **Đánh giá Định giá / Tín dụng**  
6. **Rủi ro Chính**  
7. **Triển vọng & Khuyến nghị**  
8. **Phụ lục & Ghi chú Dữ liệu**  

+ Bảng chỉ số tóm tắt + nguồn tham chiếu  
→ Xuất **PDF** (header/footer chuyên nghiệp), Markdown, Excel.

---

## Cài đặt nhanh

```bash
git clone <repo>
cd Vietnam-Research-Agent
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Điền GROQ_API_KEY hoặc OPENAI_API_KEY vào .env
uvicorn app.main:app --reload --port 8000
```

Mở: http://localhost:8000  (UI) hoặc http://localhost:8000/docs (Swagger)

---

## API chính

### Chạy đồng bộ (khuyến nghị)

```http
POST /api/v1/research/run/sync
Content-Type: application/json

{
  "query": "Phân tích sâu Vinamilk năm 2024-2025, đánh giá định giá và rủi ro",
  "company": {
    "name": "Vinamilk",
    "ticker": "VNM"
  },
  "depth": "standard",
  "include_macro": true,
  "export_pdf": true,
  "export_excel": true
}
```

### Công ty chưa niêm yết

```json
{
  "query": "Đánh giá tín dụng Công ty TNHH ABC",
  "company": {
    "name": "Công ty TNHH ABC",
    "tax_code": "0123456789"
  },
  "depth": "standard"
}
```

### Job nền

```http
POST /api/v1/research/run
→ { "job_id": "..." }

GET /api/v1/research/jobs/{job_id}
```

### Tải báo cáo

```http
GET /api/v1/reports/list
GET /api/v1/reports/download/{filename}
```

---

## Kiến trúc

```
app/
  agents/          # Orchestrator – multi-step research pipeline
  analysis/        # Ratio engine + professional prompts
  tools/           # Macro (NSO/NHNN) + Company (any entity)
  reporting/       # PDF (ReportLab) + Markdown + Excel
  llm/             # Groq primary + OpenAI fallback
  api/v1/          # FastAPI routes
  models/          # Pydantic schemas
  core/            # Config & logging
```

**Pipeline:**
1. Định danh công ty (ticker / tên / MST)  
2. Thu thập vĩ mô (NSO + NHNN)  
3. Thu thập / parse dữ liệu công ty  
4. Tính chỉ số tài chính  
5. Sinh từng section bằng LLM (Exec → Financial → Risks → Outlook)  
6. Xuất PDF + MD + XLSX  

---

## Deploy (Render)

1. Push repo  
2. New → Blueprint → chọn `render.yaml`  
3. Set env `GROQ_API_KEY`  
4. Deploy  

---

## Lưu ý

- Dữ liệu công ty chưa niêm yết thường hạn chế trên nguồn công khai → báo cáo vẫn chạy được nhưng confidence thấp hơn; khuyến nghị bổ sung BCTC thủ công.  
- PDF dùng ReportLab (không phụ thuộc WeasyPrint runtime nặng).  
- LLM: ưu tiên Groq (nhanh, rẻ); fallback OpenAI khi rate-limit.  

---

**Vietnam Research Desk** – Professional. Data-driven. Bank-grade.
