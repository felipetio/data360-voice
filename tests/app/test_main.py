"""Smoke tests for the FastAPI app startup."""

import os

import pytest


@pytest.fixture(autouse=True)
def set_required_env_vars(monkeypatch):
    """Provide required env vars so Settings loads without a .env file."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@localhost:5432/testdb")
    monkeypatch.setenv("MCP_SERVER_URL", "http://localhost:8001")


def test_fastapi_app_imports_without_error():
    """The FastAPI app module should be importable when env vars are set."""
    # Force re-evaluation with the monkeypatched env vars in place
    import importlib

    import app.config
    import app.main

    importlib.reload(app.config)
    importlib.reload(app.main)

    from app.main import app  # intentional late import after reload

    assert app is not None
    assert app.title == "Data360 Voice"


def test_fastapi_app_has_correct_title(set_required_env_vars):
    """FastAPI app title should be 'Data360 Voice'."""
    # Ensure env is set before importing config
    os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
    os.environ.setdefault("DATABASE_URL", "postgresql://user:password@localhost:5432/testdb")

    from app.main import app

    assert app.title == "Data360 Voice"


def test_config_loads_with_valid_env(monkeypatch):
    """Settings should load successfully when all required env vars are present."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    monkeypatch.setenv("MCP_SERVER_URL", "http://mcp.example.com:8001")

    import importlib

    import app.config

    importlib.reload(app.config)

    from app.config import Settings

    settings = Settings()
    assert settings.anthropic_api_key == "sk-ant-test"
    assert settings.database_url == "postgresql://user:pass@localhost:5432/db"
    assert settings.mcp_server_url == "http://mcp.example.com:8001"


def test_config_default_mcp_server_url(monkeypatch):
    """MCP_SERVER_URL should default to http://localhost:8001 if not set."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    monkeypatch.delenv("MCP_SERVER_URL", raising=False)

    from app.config import Settings

    settings = Settings()
    assert settings.mcp_server_url == "http://localhost:8001"
