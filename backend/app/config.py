from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Core
    app_name: str = "AI Code Review & Documentation Generator"
    database_url: str = "sqlite:///./codereview.db"

    # Anthropic / Claude
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-6"
    anthropic_max_tokens: int = 16000

    # GitHub integration
    github_token: str | None = None
    github_api_url: str = "https://api.github.com"
    github_webhook_secret: str | None = None

    @property
    def llm_enabled(self) -> bool:
        """True when a Claude API key is configured. Otherwise the engine
        falls back to the local heuristic reviewer."""
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
