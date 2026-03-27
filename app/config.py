from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str
    database_url: str
    mcp_server_url: str = "http://localhost:8001"  # default for local dev
    claude_model: str = "claude-haiku-4-5"
    conversation_history_limit: int = Field(default=10, ge=1)  # must be ≥1 to bound context window


settings = Settings()
