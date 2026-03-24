"""Tests verifying Story 1.1: Project Setup and Configuration."""

import importlib
from pathlib import Path

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
    from mcp_server.config import (
        BASE_URL,
        MAX_RECORDS,
        MAX_RETRIES,
        PAGE_SIZE,
        REQUEST_TIMEOUT,
        RETRY_BACKOFF_BASE,
    )

    assert BASE_URL == "https://data360api.worldbank.org"
    assert PAGE_SIZE == 1000
    assert MAX_RECORDS == 5000
    assert REQUEST_TIMEOUT == 30
    assert MAX_RETRIES == 3
    assert RETRY_BACKOFF_BASE == 1.0


def test_modules_importable():
    client = importlib.import_module("mcp_server.data360_client")
    assert hasattr(client, "Data360Client")

    server = importlib.import_module("mcp_server.server")
    assert hasattr(server, "mcp")
