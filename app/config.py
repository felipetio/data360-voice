import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str
    database_url: str
    mcp_server_url: str = "http://localhost:8001"  # default for local dev
    claude_model: str = "claude-haiku-4-5"
    claude_max_tokens: int = Field(default=4096, ge=1)
    tool_result_max_chars: int = Field(default=50000, ge=1000)
    max_tool_rounds: int = Field(default=20, ge=1)
    conversation_history_limit: int = Field(default=10, ge=1)  # must be ≥1 to bound context window

    # RAG feature flag — set via DATA360_RAG_ENABLED env var
    rag_enabled: bool = False
    # RAG upload settings
    rag_max_upload_mb: int = int(os.getenv("DATA360_RAG_MAX_UPLOAD_MB", "20"))


settings = Settings(
    rag_enabled=os.getenv("DATA360_RAG_ENABLED", "false").lower() == "true",
)
