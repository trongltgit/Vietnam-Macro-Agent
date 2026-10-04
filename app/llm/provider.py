"""
Multi-provider LLM client with automatic failover / circuit breaker.
Primary: Groq. Designed to easily add OpenRouter or other providers later.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMError(Exception):
    """Base LLM error."""


class RateLimitError(LLMError):
    """Raised when provider returns rate limit (429)."""


class LLMProvider:
    """
    Production LLM provider with:
    - Primary model (Groq)
    - Automatic fallback to other Groq models on failure / rate-limit
    - Simple circuit breaker per model
    - Retry with exponential backoff
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._models: Dict[str, BaseChatModel] = {}
        self._failure_count: Dict[str, int] = {}
        self._last_failure_time: Dict[str, float] = {}
        self._circuit_open_until: Dict[str, float] = {}
        self._init_models()

    def _init_models(self) -> None:
        """Initialize primary + fallback models (all on Groq for now)."""
        if not (self.settings.groq_api_key or "").strip():
            raise LLMError(
                "GROQ_API_KEY is empty. Set it in Render Environment Variables."
            )
        models_to_load = [self.settings.primary_llm_model] + self.settings.fallback_models_list
        seen = set()

        for model_name in models_to_load:
            if model_name in seen:
                continue
            seen.add(model_name)
            try:
                self._models[model_name] = ChatGroq(
                    api_key=self.settings.groq_api_key,
                    model=model_name,
                    temperature=self.settings.llm_temperature,
                    max_tokens=self.settings.llm_max_tokens,
                    timeout=self.settings.llm_timeout,
                    max_retries=0,  # we handle retries ourselves
                )
                self._failure_count[model_name] = 0
                self._last_failure_time[model_name] = 0.0
                self._circuit_open_until[model_name] = 0.0
                logger.info("llm_model_initialized", model=model_name)
            except Exception as e:
                logger.warning("llm_model_init_failed", model=model_name, error=str(e))

        if not self._models:
            raise LLMError("No LLM models could be initialized. Check GROQ_API_KEY.")

    def _is_circuit_open(self, model_name: str) -> bool:
        return time.time() < self._circuit_open_until.get(model_name, 0.0)

    def _record_failure(self, model_name: str, is_rate_limit: bool = False) -> None:
        self._failure_count[model_name] = self._failure_count.get(model_name, 0) + 1
        self._last_failure_time[model_name] = time.time()

        # Open circuit longer on rate limit
        open_seconds = 60 if is_rate_limit else 30
        if self._failure_count[model_name] >= 3 or is_rate_limit:
            self._circuit_open_until[model_name] = time.time() + open_seconds
            logger.warning(
                "llm_circuit_opened",
                model=model_name,
                open_seconds=open_seconds,
                failures=self._failure_count[model_name],
            )

    def _record_success(self, model_name: str) -> None:
        self._failure_count[model_name] = 0
        self._circuit_open_until[model_name] = 0.0

    def _get_available_models(self) -> List[str]:
        available = []
        for name in self._models:
            if not self._is_circuit_open(name):
                available.append(name)
        # If all circuits open, reset the least recently failed one
        if not available and self._models:
            least_recent = min(
                self._models.keys(),
                key=lambda m: self._last_failure_time.get(m, 0.0),
            )
            self._circuit_open_until[least_recent] = 0.0
            available = [least_recent]
            logger.info("llm_circuit_force_reset", model=least_recent)
        return available

    @retry(
        retry=retry_if_exception_type((RateLimitError, LLMError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def invoke(
        self,
        messages: List[BaseMessage],
        preferred_model: Optional[str] = None,
    ) -> str:
        """
        Invoke LLM with automatic model switching.
        Returns the content string of the response.
        """
        candidates = self._get_available_models()
        if preferred_model and preferred_model in candidates:
            # Move preferred to front
            candidates = [preferred_model] + [m for m in candidates if m != preferred_model]

        last_error: Optional[Exception] = None

        for model_name in candidates:
            try:
                logger.debug("llm_invoke_start", model=model_name)
                llm = self._models[model_name]
                response = llm.invoke(messages)
                content = response.content if hasattr(response, "content") else str(response)
                self._record_success(model_name)
                logger.info("llm_invoke_success", model=model_name, chars=len(content))
                return content
            except Exception as e:
                error_str = str(e).lower()
                is_rate_limit = "429" in error_str or "rate limit" in error_str or "rate_limit" in error_str
                self._record_failure(model_name, is_rate_limit=is_rate_limit)
                last_error = e
                logger.warning(
                    "llm_invoke_failed",
                    model=model_name,
                    error=str(e),
                    is_rate_limit=is_rate_limit,
                )
                if is_rate_limit:
                    raise RateLimitError(f"Rate limit on {model_name}: {e}") from e
                continue

        raise LLMError(f"All LLM models failed. Last error: {last_error}")

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        preferred_model: Optional[str] = None,
    ) -> str:
        """Convenience method for simple system + user chat."""
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        return self.invoke(messages, preferred_model=preferred_model)

    def get_status(self) -> Dict[str, Any]:
        """Return current status of all models (for /health endpoint)."""
        now = time.time()
        status = {}
        for name in self._models:
            status[name] = {
                "available": not self._is_circuit_open(name),
                "failures": self._failure_count.get(name, 0),
                "circuit_open_remaining_sec": max(
                    0, int(self._circuit_open_until.get(name, 0) - now)
                ),
            }
        return {
            "primary": self.settings.primary_llm_model,
            "models": status,
        }


# Singleton
_llm_provider: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    global _llm_provider
    if _llm_provider is None:
        _llm_provider = LLMProvider()
    return _llm_provider
