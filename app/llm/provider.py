"""LLM provider with multi-backend fallback (Groq primary, OpenAI fallback)."""

from __future__ import annotations

from typing import Any, List, Optional

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMProvider:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._clients: dict = {}
        self._init_clients()

    def _init_clients(self) -> None:
        # Groq
        if self.settings.groq_api_key:
            try:
                from langchain_groq import ChatGroq
                self._clients["groq"] = ChatGroq(
                    api_key=self.settings.groq_api_key,
                    model=self.settings.llm_model_groq,
                    temperature=self.settings.llm_temperature,
                    max_tokens=self.settings.llm_max_tokens,
                )
                logger.info("llm_client_ready", provider="groq")
            except Exception as e:
                logger.warning("llm_groq_init_failed", error=str(e))

        # OpenAI
        if self.settings.openai_api_key:
            try:
                from langchain_openai import ChatOpenAI
                self._clients["openai"] = ChatOpenAI(
                    api_key=self.settings.openai_api_key,
                    model=self.settings.llm_model_openai,
                    temperature=self.settings.llm_temperature,
                    max_tokens=self.settings.llm_max_tokens,
                )
                logger.info("llm_client_ready", provider="openai")
            except Exception as e:
                logger.warning("llm_openai_init_failed", error=str(e))

    @property
    def available(self) -> List[str]:
        return list(self._clients.keys())

    def generate(
        self,
        system: str,
        user: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate text with automatic fallback."""
        order = []
        primary = self.settings.llm_primary
        if primary in self._clients:
            order.append(primary)
        for k in self._clients:
            if k not in order:
                order.append(k)

        if not order:
            logger.error("no_llm_available")
            return ""

        last_err = None
        for name in order:
            try:
                client = self._clients[name]
                messages = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ]
                # LangChain chat models
                from langchain_core.messages import SystemMessage, HumanMessage
                resp = client.invoke(
                    [SystemMessage(content=system), HumanMessage(content=user)]
                )
                text = resp.content if hasattr(resp, "content") else str(resp)
                return (text or "").strip()
            except Exception as e:
                last_err = e
                logger.warning("llm_call_failed", provider=name, error=str(e))
                continue

        logger.error("all_llm_failed", error=str(last_err))
        return ""

    def status(self) -> dict:
        return {
            "available": self.available,
            "primary": self.settings.llm_primary,
            "ready": len(self._clients) > 0,
        }


_provider: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = LLMProvider()
    return _provider
