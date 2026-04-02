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

    # RAG settings — controlled via DATA360_RAG_ENABLED / DATA360_RAG_MAX_UPLOAD_MB env vars.
    # Pydantic-settings handles .env parsing and type coercion (bool/int), so these work
    # consistently whether the value comes from the environment, .env file, or test fixtures.
    rag_enabled: bool = Field(default=False, alias="data360_rag_enabled", validation_alias="DATA360_RAG_ENABLED")
    rag_max_upload_mb: int = Field(
        default=20, ge=1, alias="data360_rag_max_upload_mb", validation_alias="DATA360_RAG_MAX_UPLOAD_MB"
    )


settings = Settings()
