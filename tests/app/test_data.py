"""Tests for app/data.py — Chainlit SQLAlchemy data layer registration (AC1, AC3)."""

import importlib
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def set_required_env_vars(monkeypatch):
    """Provide required env vars so Settings loads without a .env file."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@localhost:5432/testdb")
    monkeypatch.setenv("MCP_SERVER_URL", "http://localhost:8001")


@pytest.fixture()
def reload_data():
    """Reload app.data after env vars are patched so settings is re-instantiated."""
    import app.config
    import app.data

    importlib.reload(app.config)
    importlib.reload(app.data)
    return app.data


class TestDataLayerRegistration:
    """AC1, AC3: Data layer is registered with SQLAlchemy and uses correct conninfo."""

    def test_get_data_layer_returns_sqlalchemy_data_layer(self, reload_data):
        """Test 1: get_data_layer() returns a SQLAlchemyDataLayer instance."""
        from chainlit.data.sql_alchemy import SQLAlchemyDataLayer

        with patch("app.data.SQLAlchemyDataLayer") as mock_layer_cls:
            mock_instance = MagicMock(spec=SQLAlchemyDataLayer)
            mock_layer_cls.return_value = mock_instance

            result = reload_data.get_data_layer()

        assert result is mock_instance
        mock_layer_cls.assert_called_once()

    def test_conninfo_has_asyncpg_protocol_added(self, reload_data):
        """Test 2: conninfo has +asyncpg protocol added when plain postgresql:// is provided."""
        captured_conninfo = []

        def capture_layer(conninfo):
            captured_conninfo.append(conninfo)
            return MagicMock()

        with patch("app.data.SQLAlchemyDataLayer", side_effect=capture_layer):
            reload_data.get_data_layer()

        assert len(captured_conninfo) == 1
        conninfo = captured_conninfo[0]
        assert "postgresql+asyncpg://" in conninfo
        assert "postgresql://" not in conninfo.replace("postgresql+asyncpg://", "")

    def test_conninfo_with_asyncpg_already_not_doubled(self, monkeypatch):
        """Test 2 (edge case): If +asyncpg is already in the URL, it's not doubled."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/testdb")

        import app.config
        import app.data

        importlib.reload(app.config)
        importlib.reload(app.data)

        captured_conninfo = []

        def capture_layer(conninfo):
            captured_conninfo.append(conninfo)
            return MagicMock()

        with patch("app.data.SQLAlchemyDataLayer", side_effect=capture_layer):
            app.data.get_data_layer()

        assert len(captured_conninfo) == 1
        conninfo = captured_conninfo[0]
        # Should not have double asyncpg
        assert conninfo.count("+asyncpg") == 1

    def test_data_layer_uses_database_url_from_settings(self, reload_data, monkeypatch):
        """Test: data layer uses DATABASE_URL from settings (NFR6)."""
        test_url = "postgresql://custom_user:custom_pass@db-host:5432/mydb"
        monkeypatch.setenv("DATABASE_URL", test_url)

        import app.config
        import app.data

        importlib.reload(app.config)
        importlib.reload(app.data)

        captured_conninfo = []

        def capture_layer(conninfo):
            captured_conninfo.append(conninfo)
            return MagicMock()

        with patch("app.data.SQLAlchemyDataLayer", side_effect=capture_layer):
            app.data.get_data_layer()

        assert len(captured_conninfo) == 1
        # The URL should be converted but contain the custom host
        assert "custom_user" in captured_conninfo[0]
        assert "db-host" in captured_conninfo[0]
        assert "mydb" in captured_conninfo[0]
        assert "postgresql+asyncpg://" in captured_conninfo[0]
