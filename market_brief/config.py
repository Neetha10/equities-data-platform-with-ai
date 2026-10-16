from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_feed: str = "sip"
    sec_user_agent: str = "EquitiesDailyBrief admin@example.com"
    llm_provider: str = "deterministic"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:3b"
    analytics_backend: str = "engine"


@lru_cache
def settings() -> Settings:
    return Settings()
