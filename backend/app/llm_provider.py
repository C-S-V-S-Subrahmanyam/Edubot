"""
Multi-Provider LLM Configuration Module

This module handles dynamic model selection between:
- OpenAI GPT-4
- Google Gemini
- Local Ollama models

Selection is controlled via user settings stored in localStorage.
"""

import os
from typing import Optional, Literal
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel
from app.config import (
    DEFAULT_AI_PROVIDER,
    DEFAULT_OPENAI_API_KEY, DEFAULT_OPENAI_MODEL,
    DEFAULT_GOOGLE_API_KEY, DEFAULT_GEMINI_MODEL,
    DEFAULT_DEEPSEEK_API_KEY, DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_OLLAMA_URL, DEFAULT_OLLAMA_MODEL,
)

ProviderType = Literal["openai", "gemini", "ollama", "deepseek", "auto"]


class LLMProvider:
    """Manages dynamic LLM provider selection and fallback."""
    
    def __init__(self):
        # Use env default provider, fall back to 'ollama'
        self.current_provider: str = DEFAULT_AI_PROVIDER if DEFAULT_AI_PROVIDER else "ollama"
        
        # Load defaults from .env, then allow runtime overrides
        self._api_keys = {
            'openai': DEFAULT_OPENAI_API_KEY or None,
            'openai_model': DEFAULT_OPENAI_MODEL or 'gpt-4o-mini',
            'gemini': DEFAULT_GOOGLE_API_KEY or None,
            'gemini_model': DEFAULT_GEMINI_MODEL or 'gemini-2.5-flash',
            'ollama_url': DEFAULT_OLLAMA_URL or 'http://localhost:11434',
            'ollama_model': DEFAULT_OLLAMA_MODEL or 'llama3.1:8b',
            'deepseek': DEFAULT_DEEPSEEK_API_KEY or None,
            'deepseek_model': DEFAULT_DEEPSEEK_MODEL or 'deepseek-chat'
        }
        
        # Track which keys came from env (for the defaults endpoint)
        self._env_defaults = {
            'openai': bool(DEFAULT_OPENAI_API_KEY),
            'gemini': bool(DEFAULT_GOOGLE_API_KEY),
            'deepseek': bool(DEFAULT_DEEPSEEK_API_KEY),
            'ollama': True,  # Ollama is always available locally
            'default_provider': self.current_provider,
        }
    
    def get_env_defaults(self) -> dict:
        """Return which providers have server-side default API keys configured."""
        return self._env_defaults.copy()
    
    def set_api_keys(
        self, 
        openai_key: str = None, 
        openai_model: str = None,
        gemini_key: str = None,
        gemini_model: str = None,
        ollama_url: str = None,
        ollama_model: str = None,
        deepseek_key: str = None,
        deepseek_model: str = None
    ):
        """Set API keys and models dynamically from user settings."""
        if openai_key:
            self._api_keys['openai'] = openai_key
        if openai_model:
            self._api_keys['openai_model'] = openai_model
        if gemini_key:
            self._api_keys['gemini'] = gemini_key
        if gemini_model:
            self._api_keys['gemini_model'] = gemini_model
        if ollama_url:
            self._api_keys['ollama_url'] = ollama_url
        if ollama_model:
            self._api_keys['ollama_model'] = ollama_model
        if deepseek_key:
            self._api_keys['deepseek'] = deepseek_key
        if deepseek_model:
            self._api_keys['deepseek_model'] = deepseek_model
    
    def get_api_keys(self) -> dict:
        """Get current API keys."""
        return self._api_keys.copy()
        
    def get_llm(
        self,
        provider: Optional[str] = None,
        temperature: float = 0.7,
        max_retries: int = 2
    ) -> BaseChatModel:
        """
        Get the LLM instance based on provider selection.
        
        Args:
            provider: Override the default AI_PROVIDER setting
            temperature: Model temperature (0.0 - 1.0)
            max_retries: Number of retry attempts on failure
            
        Returns:
            BaseChatModel: Configured LLM instance
            
        Raises:
            ValueError: If provider is invalid or credentials missing
        """
        provider = (provider or self.current_provider).lower()
        
        if provider == "auto":
            return self._get_auto_provider(temperature, max_retries)
        elif provider == "openai":
            return self._get_openai(temperature, max_retries)
        elif provider == "gemini":
            return self._get_gemini(temperature, max_retries)
        elif provider == "ollama":
            return self._get_ollama(temperature, max_retries)
        elif provider == "deepseek":
            return self._get_deepseek(temperature, max_retries)
        else:
            raise ValueError(
                f"Invalid AI provider: {provider}. "
                f"Must be one of: openai, gemini, ollama, deepseek, auto"
            )
    
    def _get_openai(self, temperature: float, max_retries: int) -> ChatOpenAI:
        """Get OpenAI GPT-4 model."""
        api_key = self._api_keys.get('openai') or os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY not configured")
        
        model = self._api_keys.get('openai_model') or 'gpt-4o-mini'
        
        # Validate supported models
        supported_models = ['gpt-4o-mini']
        if model not in supported_models:
            raise ValueError(f"Model '{model}' is not supported. Please use GPT-4o Mini for optimal performance.")
        
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            max_retries=max_retries,
            openai_api_key=api_key,
        )
    
    def _get_gemini(self, temperature: float, max_retries: int) -> ChatGoogleGenerativeAI:
        """Get Google Gemini model."""
        api_key = self._api_keys.get('gemini') or os.getenv('GOOGLE_API_KEY')
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not configured")
        
        model = self._api_keys.get('gemini_model') or 'gemini-2.5-flash'
        
        # Validate supported models
        supported_models = [
            'gemini-2.5-flash',
            'gemini-flash-latest',
            'gemini-1.5-flash',
            'gemini-1.5-flash-latest',
        ]
        if model not in supported_models:
            raise ValueError(
                f"Model '{model}' is not supported. Please use Gemini 1.5 Flash, Gemini 2.5 Flash, or Gemini Flash Latest for optimal performance."
            )
        
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            max_retries=max_retries,
            google_api_key=api_key,
        )
    
    def _get_ollama(self, temperature: float, max_retries: int) -> ChatOllama:
        """Get Ollama local model."""
        base_url = self._api_keys.get('ollama_url') or 'http://localhost:11434'
        model = self._api_keys.get('ollama_model') or 'llama3.1:8b'
        
        return ChatOllama(
            model=model,
            temperature=temperature,
            max_retries=max_retries,
            base_url=base_url,
        )

    def _get_deepseek(self, temperature: float, max_retries: int) -> ChatOpenAI:
        """Get DeepSeek model via OpenAI-compatible API."""
        api_key = self._api_keys.get('deepseek') or os.getenv('DEEPSEEK_API_KEY')
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY not configured")

        model = self._api_keys.get('deepseek_model') or 'deepseek-chat'
        supported_models = ['deepseek-chat', 'deepseek-reasoner']
        if model not in supported_models:
            raise ValueError(
                f"Model '{model}' is not supported. "
                f"Please use one of: {', '.join(supported_models)}."
            )

        return ChatOpenAI(
            model=model,
            temperature=temperature,
            max_retries=max_retries,
            openai_api_key=api_key,
            openai_api_base="https://api.deepseek.com/v1",
        )

    def _get_auto_provider(self, temperature: float, max_retries: int) -> BaseChatModel:
        """
        Auto-select provider with fallback priority:
        1. University-provided API (from .env)
        2. User-provided API keys (from settings)
        3. Ollama (local fallback)
        """
        # Try university-provided OpenAI first
        env_openai = os.getenv('OPENAI_API_KEY')
        if env_openai:
            try:
                return self._get_openai(temperature, max_retries)
            except Exception as e:
                print(f"University OpenAI failed: {e}, trying other providers...")
        
        # Try user-provided OpenAI
        if self._api_keys.get('openai'):
            try:
                return self._get_openai(temperature, max_retries)
            except Exception as e:
                print(f"User OpenAI failed: {e}, trying Gemini...")
        
        # Try university-provided Gemini
        env_gemini = os.getenv('GOOGLE_API_KEY')
        if env_gemini:
            try:
                return self._get_gemini(temperature, max_retries)
            except Exception as e:
                print(f"University Gemini failed: {e}, trying other providers...")
        
        # Try user-provided Gemini
        if self._api_keys.get('gemini'):
            try:
                return self._get_gemini(temperature, max_retries)
            except Exception as e:
                print(f"User Gemini failed: {e}, trying DeepSeek...")

        # Try environment-provided DeepSeek
        env_deepseek = os.getenv('DEEPSEEK_API_KEY')
        if env_deepseek:
            try:
                return self._get_deepseek(temperature, max_retries)
            except Exception as e:
                print(f"DeepSeek env key failed: {e}, trying user DeepSeek...")

        # Try user-provided DeepSeek
        if self._api_keys.get('deepseek'):
            try:
                return self._get_deepseek(temperature, max_retries)
            except Exception as e:
                print(f"User DeepSeek failed: {e}, trying Ollama...")

        # Fallback to Ollama (local)
        return self._get_ollama(temperature, max_retries)
    
    def set_provider(self, provider: str):
        """Update the current provider setting."""
        if provider.lower() not in ["openai", "gemini", "ollama", "deepseek", "auto"]:
            raise ValueError(f"Invalid provider: {provider}")
        self.current_provider = provider.lower()
    
    def get_current_provider(self) -> str:
        """Get the currently active provider."""
        return self.current_provider
    
    def supports_tools_for(self, provider: Optional[str] = None) -> bool:
        """Check whether a specific provider can use tool/function calling."""
        provider_name = (provider or self.current_provider).lower()

        if provider_name in ("openai", "gemini", "deepseek"):
            print(f"[TOOL SUPPORT] Provider '{provider_name}' supports tools: YES")
            return True

        if provider_name == "ollama":
            # Some Ollama models don't support tools.
            model = self._api_keys.get('ollama_model') or os.getenv('OLLAMA_MODEL', 'llama3.1:8b')
            model_lower = model.lower()
            non_tool_models = ['gemma', 'phi', 'tinyllama', 'stablelm']
            supports = not any(nm in model_lower for nm in non_tool_models)
            print(f"[TOOL SUPPORT] Ollama model '{model}' supports tools: {supports}")
            return supports

        if provider_name == "auto":
            resolved_provider = self._resolve_auto_provider()
            print(f"[TOOL SUPPORT] Auto-resolved to provider: '{resolved_provider}'")
            return self.supports_tools_for(resolved_provider)

        print(f"[TOOL SUPPORT] Unknown provider '{provider_name}': NO")
        return False

    def supports_tools(self) -> bool:
        """Check if the current model supports tool/function calling."""
        return self.supports_tools_for(self.current_provider)
    
    def _resolve_auto_provider(self) -> str:
        """Determine which provider auto-select would pick without creating an LLM."""
        if os.getenv('OPENAI_API_KEY') or self._api_keys.get('openai'):
            return "openai"
        if os.getenv('GOOGLE_API_KEY') or self._api_keys.get('gemini'):
            return "gemini"
        if os.getenv('DEEPSEEK_API_KEY') or self._api_keys.get('deepseek'):
            return "deepseek"
        return "ollama"
    
    def get_available_providers(self) -> dict[str, bool]:
        """Check which providers are available based on configuration."""
        return {
            "openai": bool(self._api_keys.get('openai') or os.getenv('OPENAI_API_KEY')),
            "gemini": bool(self._api_keys.get('gemini') or os.getenv('GOOGLE_API_KEY')),
            "deepseek": bool(self._api_keys.get('deepseek') or os.getenv('DEEPSEEK_API_KEY')),
            "ollama": True,  # Always available if Ollama is running
        }


# Global provider instance
llm_provider = LLMProvider()


def get_current_llm(temperature: float = 0.7, max_retries: int = 2) -> BaseChatModel:
    """
    Convenience function to get the currently configured LLM.
    
    Usage:
        llm = get_current_llm()
        response = llm.invoke("Hello!")
    """
    return llm_provider.get_llm(temperature=temperature, max_retries=max_retries)
