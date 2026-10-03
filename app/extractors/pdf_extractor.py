import logging
from pathlib import Path
from pypdf import PdfReader

logger = logging.getLogger(__name__)

class PDFExtractor:
    @staticmethod
    def extract_text_from_pdf(file_path: str, max_pages: int = 25) -> str:
        text_content = []
        path = Path(file_path)
        if not path.exists():
            logger.error(f"File PDF không tồn tại tại đường dẫn: {file_path}")
            return ""

        try:
            reader = PdfReader(str(path))
            num_pages = min(len(reader.pages), max_pages)
            for index in range(num_pages):
                page = reader.pages[index]
                text = page.extract_text()
                if text:
                    text_content.append(f"--- Trang {index + 1} ---
{text}")
            logger.info(f"Đã trích xuất thành công {num_pages} trang từ {path.name}")
            return "\n".join(text_content)
        except Exception as e:
            logger.error(f"Lỗi đọc file PDF {file_path}: {str(e)}")
            return ""
