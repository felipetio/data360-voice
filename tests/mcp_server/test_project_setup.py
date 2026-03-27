"""Tests verifying Story 1.1: Project Setup and Configuration."""

import importlib
import os
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).parent.parent.parent


def test_project_files_exist():
    expected = [
        "pyproject.toml",
        ".env.example",
        ".gitignore",
        "mcp_server/__init__.py",
        "mcp_server/server.py",
        "mcp_server/data360_client.py",
        "mcp_server/config.py",
        "tests/__init__.py",
        "tests/mcp_server/__init__.py",
    ]
    for path in expected:
        assert (PROJECT_ROOT / path).exists(), f"Missing: {path}"
    assert (PROJECT_ROOT / "tests" / "mcp_server" / "fixtures").is_dir()


def test_config_defaults():
    # Remove env vars that override defaults (e.g. from .env file)
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith(("DATA360_", "MCP_"))}
    with patch.dict(os.environ, clean_env, clear=True), patch("dotenv.load_dotenv"):
        import mcp_server.config as cfg

        importlib.reload(cfg)

        assert cfg.BASE_URL == "https://data360api.worldbank.org"
        assert cfg.PAGE_SIZE == 1000
        assert cfg.MAX_RECORDS == 5000
        assert cfg.REQUEST_TIMEOUT == 30.0
        assert cfg.MAX_RETRIES == 3
        assert cfg.RETRY_BACKOFF_BASE == 1.0
        assert cfg.MCP_TRANSPORT == "stdio"
        assert cfg.MCP_PORT is None


def test_modules_importable():
    client = importlib.import_module("mcp_server.data360_client")
    assert hasattr(client, "Data360Client")

    server = importlib.import_module("mcp_server.server")
    assert hasattr(server, "mcp")
