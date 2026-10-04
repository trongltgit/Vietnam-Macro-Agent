"""
Application configuration using pydantic-settings.
"""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = Field(default="production", alias="APP_ENV")
    app_name: str = Field(default="Vietnam Macro AI Agent", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    data_dir: Path = Field(default=Path("./data"), alias="DATA_DIR")
    raw_dir: Path = Field(default=Path("./data/raw"), alias="RAW_DIR")
    processed_dir: Path = Field(default=Path("./data/processed"), alias="PROCESSED_DIR")
    excel_phase1_dir: Path = Field(default=Path("./data/excel_phase1"), alias="EXCEL_PHASE1_DIR")
    excel_phase1_file: str = Field(default="phase1_workbook.xlsx", alias="EXCEL_PHASE1_FILE")

    # Optional at boot — required when calling LLM
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    primary_llm_provider: str = Field(default="groq", alias="PRIMARY_LLM_PROVIDER")
    primary_llm_model: str = Field(
        default="llama-3.3-70b-versatile", alias="PRIMARY_LLM_MODEL"
    )
    fallback_llm_models: str = Field(
        default="openai/gpt-oss-120b,llama-3.1-8b-instant",
        alias="FALLBACK_LLM_MODELS",
    )
    llm_temperature: float = Field(default=0.1, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=4096, alias="LLM_MAX_TOKENS")
    llm_timeout: int = Field(default=60, alias="LLM_TIMEOUT")
    llm_max_retries: int = Field(default=3, alias="LLM_MAX_RETRIES")

    groq_rpm_limit: int = Field(default=30, alias="GROQ_RPM_LIMIT")
    groq_rpd_limit: int = Field(default=1000, alias="GROQ_RPD_LIMIT")

    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")

    agent_max_iterations: int = Field(default=8, alias="AGENT_MAX_ITERATIONS")
    agent_timeout: int = Field(default=300, alias="AGENT_TIMEOUT")

    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    workers: int = Field(default=1, alias="WORKERS")

    @property
    def fallback_models_list(self) -> List[str]:
        return [m.strip() for m in self.fallback_llm_models.split(",") if m.strip()]

    @property
    def excel_phase1_path(self) -> Path:
        return self.excel_phase1_dir / self.excel_phase1_file

    def ensure_directories(self) -> None:
        for d in [
            self.data_dir,
            self.raw_dir,
            self.processed_dir,
            self.excel_phase1_dir,
            self.raw_dir / "nhnn",
            self.raw_dir / "nso",
            self.raw_dir / "companies",
            self.raw_dir / "other",
            self.processed_dir / "macro",
            self.processed_dir / "exchange_rate",
            self.processed_dir / "trade",
        ]:
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
