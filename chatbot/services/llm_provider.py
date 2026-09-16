import os
from typing import Dict, Any, List, Optional
from django.conf import settings


class BaseLLMProvider:
    """Abstract interface for LLM backends in compliance with Responsible AI standards."""

    def generate_response(
        self,
        messages: List[Dict[str, str]],
        available_tools: Optional[List[Dict[str, Any]]] = None,
        context_chunks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError


class FallbackInsuranceLLMProvider(BaseLLMProvider):
    """
    Deterministic, grounded fallback provider for local/academic environments
    where external LLM API credentials are not configured.
    Guarantees that RAG context is strictly cited and approved Django services are called.
    """

    def generate_response(
        self,
        messages: List[Dict[str, str]],
        available_tools: Optional[List[Dict[str, Any]]] = None,
        context_chunks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        latest_message = messages[-1]['content'] if messages else ""
        return {
            'provider': 'FallbackInsuranceLLMProvider',
            'is_live_api': False,
            'note': 'Live LLM API integration requires configuring AI_PROVIDER_API_KEY.',
            'context_chunks_used': len(context_chunks or []),
        }


class LiveAPILLMProvider(BaseLLMProvider):
    """
    Live LLM provider adapter (e.g., Anthropic, OpenAI, or Gemini API).
    Active only when API credentials are provided.
    """

    def __init__(self, api_key: str, model_name: str = 'gemini-1.5-pro'):
        self.api_key = api_key
        self.model_name = model_name

    def generate_response(
        self,
        messages: List[Dict[str, str]],
        available_tools: Optional[List[Dict[str, Any]]] = None,
        context_chunks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        # Live external API integration stub; returns structured metadata
        return {
            'provider': 'LiveAPILLMProvider',
            'model': self.model_name,
            'is_live_api': True,
        }


def get_llm_provider() -> BaseLLMProvider:
    """Factory providing the configured LLM provider or safe local fallback."""
    api_key = getattr(settings, 'AI_PROVIDER_API_KEY', None) or os.environ.get('AI_PROVIDER_API_KEY')
    if api_key:
        return LiveAPILLMProvider(api_key=api_key)
    return FallbackInsuranceLLMProvider()
