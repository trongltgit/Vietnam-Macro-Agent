"""
Professional research prompts – style of commercial bank research /
government policy notes / large conglomerate financial reviews.
"""

SYSTEM_RESEARCH_ANALYST = """Bạn là Senior Equity & Credit Research Analyst tại một ngân hàng thương mại lớn tại Việt Nam (mức độ CFA / FRM).

Nhiệm vụ: viết báo cáo phân tích chuyên sâu, khách quan, dựa trên dữ liệu được cung cấp.
Tuyệt đối tuân thủ các nguyên tắc sau:

1. CHỈ sử dụng số liệu và thông tin được cung cấp trong context. Không bịa số.
2. Nếu thiếu dữ liệu → ghi rõ "Chưa có dữ liệu công khai" và đánh giá tác động.
3. Văn phong: trang trọng, súc tích, chuyên nghiệp (giống research note của SSI, VinaCapital, Vietcombank Research, NHNN, Bộ KH&ĐT).
4. Cấu trúc rõ ràng, dùng tiêu đề số, bullet khi cần.
5. Phân tích phải có chiều sâu: xu hướng, so sánh, nguyên nhân, rủi ro, triển vọng.
6. Kết luận phải có quan điểm rõ ràng (tích cực / trung lập / thận trọng) kèm lý do.
7. Không thêm URL hay link. Không thêm disclaimer dài dòng.
8. Ngôn ngữ: Tiếng Việt chuyên ngành tài chính.
"""


def build_executive_summary_prompt(
    query: str,
    company_name: str,
    macro_text: str,
    key_figures_text: str,
    depth: str,
) -> tuple[str, str]:
    system = SYSTEM_RESEARCH_ANALYST
    user = f"""Viết **Executive Summary** (tóm tắt điều hành) cho báo cáo nghiên cứu.

Yêu cầu gốc: {query}
Công ty / đối tượng: {company_name}
Độ sâu: {depth}

Dữ liệu vĩ mô:
{macro_text}

Chỉ số / số liệu chính:
{key_figures_text}

Yêu cầu format:
- Độ dài: 180–280 từ.
- 4–6 câu then chốt: (1) Bối cảnh, (2) Điểm nổi bật tài chính, (3) Điểm mạnh/yếu, (4) Rủi ro chính, (5) Quan điểm / khuyến nghị ngắn.
- Không dùng bullet trong phần này. Viết đoạn văn mạch lạc.
- Kết thúc bằng 1 câu quan điểm rõ ràng (Tích cực / Trung lập / Thận trọng).
"""
    return system, user


def build_financial_analysis_prompt(
    company_name: str,
    key_figures_text: str,
    ratios_text: str,
    financials_text: str,
) -> tuple[str, str]:
    system = SYSTEM_RESEARCH_ANALYST
    user = f"""Viết phần **Phân tích Tài chính** chuyên sâu cho {company_name}.

Số liệu thô:
{key_figures_text}

Chỉ số tài chính:
{ratios_text}

Chuỗi thời gian (nếu có):
{financials_text}

Yêu cầu:
- Phân tích khả năng sinh lời (margin, ROE, ROA) và xu hướng.
- Phân tích đòn bẩy & thanh khoản.
- Đánh giá chất lượng lợi nhuận và dòng tiền (nếu có).
- So sánh nội bộ theo thời gian nếu có số liệu nhiều kỳ.
- Chỉ ra điểm mạnh / điểm yếu cụ thể bằng số.
- Độ dài 350–500 từ, có tiêu đề phụ nếu cần.
"""
    return system, user


def build_risks_outlook_prompt(
    company_name: str,
    industry: str,
    macro_text: str,
    key_points: str,
) -> tuple[str, str]:
    system = SYSTEM_RESEARCH_ANALYST
    user = f"""Viết hai phần: **Rủi ro chính** và **Triển vọng & Khuyến nghị** cho {company_name}.

Ngành: {industry or "Chưa xác định"}
Bối cảnh vĩ mô:
{macro_text}

Điểm chính đã phân tích:
{key_points}

Yêu cầu:
### Rủi ro chính
- Liệt kê 4–6 rủi ro quan trọng nhất (thị trường, tín dụng, vận hành, pháp lý, vĩ mô...).
- Mỗi rủi ro: mô tả ngắn + mức độ (Cao/Trung bình/Thấp) + biện pháp giảm thiểu nếu có.

### Triển vọng & Khuyến nghị
- Triển vọng 12–24 tháng.
- Quan điểm rõ: Tích cực / Trung lập / Thận trọng (hoặc Buy/Hold/Sell nếu là cổ phiếu).
- 2–3 điều kiện / catalyst cần theo dõi.
- Độ dài tổng 300–450 từ.
"""
    return system, user


def build_full_report_prompt(
    query: str,
    company_name: str,
    profile_text: str,
    macro_text: str,
    key_figures_text: str,
    ratios_text: str,
    depth: str,
) -> tuple[str, str]:
    """Single-shot full professional report when multi-step is not used."""
    system = SYSTEM_RESEARCH_ANALYST
    user = f"""Hãy viết một **Báo cáo Phân tích Chuyên sâu** hoàn chỉnh theo format research note ngân hàng thương mại.

Yêu cầu gốc của khách: {query}
Đối tượng: {company_name}
Độ sâu yêu cầu: {depth}

=== THÔNG TIN CÔNG TY ===
{profile_text}

=== DỮ LIỆU VĨ MÔ ===
{macro_text}

=== SỐ LIỆU TÀI CHÍNH / CHỈ SỐ ===
{key_figures_text}

=== CHỈ SỐ TÍNH TOÁN ===
{ratios_text}

=== CẤU TRÚC BẮT BUỘC ===
1. TÓM TẮT ĐIỀU HÀNH (Executive Summary)
2. TỔNG QUAN DOANH NGHIỆP & MÔ HÌNH KINH DOANH
3. PHÂN TÍCH TÀI CHÍNH
4. LIÊN KẾT VĨ MÔ – NGÀNH
5. ĐÁNH GIÁ ĐỊNH GIÁ / TÍN DỤNG (tùy loại hình)
6. RỦI RO CHÍNH
7. TRIỂN VỌNG & KHUYẾN NGHỊ
8. PHỤ LỤC / GHI CHÚ DỮ LIỆU

Quy tắc:
- Chỉ dùng số liệu đã cho. Thiếu thì ghi rõ.
- Phân tích phải có chiều sâu, không liệt kê suông.
- Văn phong trang trọng, chuyên nghiệp.
- Tổng độ dài mục tiêu: 1200–2000 từ cho depth=standard, dài hơn nếu depth=deep.
- Không chèn URL.
"""
    return system, user


def build_business_overview_prompt(company_name: str, profile_text: str, query: str) -> tuple[str, str]:
    system = SYSTEM_RESEARCH_ANALYST
    user = f"""Viết phần **Tổng quan Doanh nghiệp & Mô hình Kinh doanh** cho {company_name}.

Thông tin hồ sơ:
{profile_text}

Bối cảnh yêu cầu: {query}

Yêu cầu:
- Lịch sử ngắn, lĩnh vực hoạt động, vị thế thị trường.
- Mô hình doanh thu / khách hàng chính / chuỗi giá trị (nếu suy luận được).
- Cổ đông lớn / ban lãnh đạo (nếu có).
- Độ dài 200–350 từ.
"""
    return system, user


def build_macro_linkage_prompt(
    company_name: str,
    industry: str,
    macro_text: str,
) -> tuple[str, str]:
    system = SYSTEM_RESEARCH_ANALYST
    user = f"""Viết phần **Liên kết Vĩ mô – Ngành** cho {company_name} (ngành: {industry or "chung"}).

Dữ liệu vĩ mô hiện tại:
{macro_text}

Yêu cầu:
- Phân tích tác động của GDP, lạm phát, tỷ giá, tín dụng, FDI tới doanh nghiệp/ngành.
- Nhạy cảm chính (xuất khẩu, nhập khẩu nguyên liệu, lãi suất, tiêu dùng...).
- Độ dài 200–320 từ.
"""
    return system, user
