import os
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from pathlib import Path

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

class OfficialSourcesCollector:
    """
    Công cụ thu thập báo cáo kinh tế vĩ mô và tài chính từ các nguồn chính thống:
    - Ngân hàng Nhà nước (SBV)
    - Tổng cục Thống kê (NSO/GSO)
    - Cổng thông tin doanh nghiệp / UBCKNN
    """

    @staticmethod
    def fetch_and_download_documents(target_urls: list[str]) -> list[dict]:
        downloaded_files = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        for url in target_urls:
            try:
                logger.info(f"Đang quét trang để tìm file báo cáo: {url}")
                response = requests.get(url, headers=headers, timeout=15)
                if response.status_code != 200:
                    logger.warning(f"Không thể truy cập {url}, status code: {response.status_code}")
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')
                
                for a_tag in soup.find_all('a', href=True):
                    href = a_tag['href']
                    lower_href = href.lower()
                    
                    if any(ext in lower_href for ext in ['.pdf', '.xlsx', '.xls', '.doc', '.docx']):
                        file_url = urljoin(url, href)
                        parsed_url = urlparse(file_url)
                        file_name = os.path.basename(parsed_url.path)
                        
                        if not file_name or len(file_name) > 100:
                            file_name = f"report_{abs(hash(file_url))}.pdf"
                        
                        local_path = DOWNLOAD_DIR / file_name
                        
                        if not local_path.exists():
                            logger.info(f"Đang tải file tài liệu: {file_url}")
                            file_resp = requests.get(file_url, headers=headers, timeout=30)
                            if file_resp.status_code == 200:
                                with open(local_path, "wb") as f:
                                    f.write(file_resp.content)
                                downloaded_files.append({
                                    "source_url": file_url,
                                    "file_name": file_name,
                                    "local_path": str(local_path)
                                })
                                logger.info(f"Đã lưu thành công file tại: {local_path}")
            except Exception as e:
                logger.error(f"Lỗi khi tải tài liệu từ {url}: {str(e)}")

        return downloaded_files

# Alias để khớp với code import OfficialSourceTool ở các module khác
OfficialSourceTool = OfficialSourcesCollector
