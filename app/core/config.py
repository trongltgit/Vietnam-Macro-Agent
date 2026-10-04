"""Application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "Vietnam Research Agent"
    app_version: str = "2.0.0"
    environment: str = "production"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # Paths
    base_dir: Path = Path(__file__).resolve().parents[2]
    raw_dir: Path = base_dir / "data" / "raw"
    processed_dir: Path = base_dir / "data" / "processed"
    reports_dir: Path = base_dir / "data" / "reports"

    # LLM – primary + fallbacks
    groq_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    llm_primary: str = "groq"  # groq | openai | anthropic
    llm_model_groq: str = "llama-3.3-70b-versatile"
    llm_model_openai: str = "gpt-4o"
    llm_temperature: float = 0.15
    llm_max_tokens: int = 8192

    # Data sources
    request_timeout: int = 30
    max_retries: int = 3
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )

    # Report
    report_language: str = "vi"  # vi | en
    report_org_name: str = "Vietnam Research Desk"
    report_disclaimer: str = (
        "Báo cáo này chỉ mang tính tham khảo, không phải khuyến nghị đầu tư. "
        "Dữ liệu được tổng hợp từ nguồn công khai và có thể không đầy đủ."
    )

    def ensure_dirs(self) -> None:
        for d in [
            self.raw_dir / "nhnn",
            self.raw_dir / "nso",
            self.raw_dir / "companies",
            self.raw_dir / "other",
            self.processed_dir,
            self.reports_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
