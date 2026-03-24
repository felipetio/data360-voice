"""Tests for Data360Client (Story 1.2)."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import httpx
import pytest

from mcp_server.data360_client import Data360Client

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def client():
    return Data360Client(base_url="https://test.api", timeout=5.0, max_retries=3, retry_backoff_base=0.01)


def _make_mock_client():
    """Create a mock httpx.AsyncClient that passes _get_client checks."""
    mock = AsyncMock()
    mock.is_closed = False
    return mock


def _mock_response(status_code: int = 200, json_data: dict | list | None = None) -> httpx.Response:
    """Create a mock httpx.Response."""
    return httpx.Response(
        status_code=status_code,
        json=json_data or {},
        request=httpx.Request("GET", "https://test.api/data360/data"),
    )


# --- Task 1: Parameter mapping ---


class TestParameterMapping:
    def test_snake_case_to_uppercase(self):
        c = Data360Client()
        assert c._map_params({"database_id": "WB_WDI", "ref_area": "BRA"}) == {
            "DATABASE_ID": "WB_WDI",
            "REF_AREA": "BRA",
        }

    def test_none_values_skipped(self):
        c = Data360Client()
        assert c._map_params({"database_id": "WB_WDI", "ref_area": None}) == {"DATABASE_ID": "WB_WDI"}

    def test_empty_params(self):
        c = Data360Client()
        assert c._map_params({}) == {}


# --- Task 2: _request with retry ---


class TestRequest:
    @pytest.mark.asyncio
    async def test_successful_get(self, client):
        mock_http = _make_mock_client()
        mock_http.request = AsyncMock(return_value=_mock_response(200, {"value": [{"OBS_VALUE": "42"}]}))
        client._client = mock_http

        result = await client._request("GET", "/data360/data", params={"DATABASE_ID": "WB_WDI"})
        assert result == {"value": [{"OBS_VALUE": "42"}]}

    @pytest.mark.asyncio
    async def test_successful_post(self, client):
        mock_http = _make_mock_client()
        mock_http.request = AsyncMock(return_value=_mock_response(200, {"results": [{"name": "CO2"}]}))
        client._client = mock_http

        result = await client._request("POST", "/data360/searchv2", json_body={"searchText": "CO2"})
        assert result == {"results": [{"name": "CO2"}]}

    @pytest.mark.asyncio
    async def test_retry_on_429(self, client):
        mock_http = _make_mock_client()
        mock_http.request = AsyncMock(
            side_effect=[_mock_response(429), _mock_response(200, {"value": []})]
        )
        client._client = mock_http

        result = await client._request("GET", "/data360/data")
        assert result == {"value": []}
        assert mock_http.request.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_503(self, client):
        mock_http = _make_mock_client()
        mock_http.request = AsyncMock(
            side_effect=[_mock_response(503), _mock_response(503), _mock_response(200, {"value": []})]
        )
        client._client = mock_http

        result = await client._request("GET", "/data360/data")
        assert result == {"value": []}
        assert mock_http.request.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted_returns_error(self, client):
        mock_http = _make_mock_client()
        mock_http.request = AsyncMock(return_value=_mock_response(503))
        client._client = mock_http

        result = await client._request("GET", "/data360/data")
        assert result["success"] is False
        assert result["error_type"] == "api_error"
        assert "503" in result["error"]

    @pytest.mark.asyncio
    async def test_no_retry_on_400(self, client):
        mock_http = _make_mock_client()
        mock_http.request = AsyncMock(return_value=_mock_response(400))
        client._client = mock_http

        result = await client._request("GET", "/data360/data")
        assert result["success"] is False
        assert result["error_type"] == "api_error"
        assert mock_http.request.call_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_404(self, client):
        mock_http = _make_mock_client()
        mock_http.request = AsyncMock(return_value=_mock_response(404))
        client._client = mock_http

        result = await client._request("GET", "/data360/data")
        assert result["success"] is False
        assert mock_http.request.call_count == 1

    @pytest.mark.asyncio
    async def test_timeout_returns_structured_error(self, client):
        mock_http = _make_mock_client()
        mock_http.request = AsyncMock(side_effect=httpx.ReadTimeout("timed out"))
        client._client = mock_http

        result = await client._request("GET", "/data360/data")
        assert result["success"] is False
        assert result["error_type"] == "timeout"

    @pytest.mark.asyncio
    async def test_network_error_returns_structured_error(self, client):
        mock_http = _make_mock_client()
        mock_http.request = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        client._client = mock_http

        result = await client._request("GET", "/data360/data")
        assert result["success"] is False
        assert result["error_type"] == "api_error"

    @pytest.mark.asyncio
    async def test_invalid_json_returns_structured_error(self, client):
        resp = httpx.Response(
            status_code=200,
            content=b"<html>not json</html>",
            request=httpx.Request("GET", "https://test.api/data360/data"),
        )
        mock_http = _make_mock_client()
        mock_http.request = AsyncMock(return_value=resp)
        client._client = mock_http

        result = await client._request("GET", "/data360/data")
        assert result["success"] is False
        assert result["error_type"] == "api_error"
        assert "Invalid JSON" in result["error"]

    @pytest.mark.asyncio
    async def test_retry_exhausted_message_includes_retry_count(self, client):
        mock_http = _make_mock_client()
        mock_http.request = AsyncMock(return_value=_mock_response(503))
        client._client = mock_http

        result = await client._request("GET", "/data360/data")
        assert result["success"] is False
        assert "3 retries" in result["error"]
        assert mock_http.request.call_count == 4  # initial + 3 retries


# --- Task 3: Paginated GET ---


class TestPaginatedGet:
    @pytest.mark.asyncio
    async def test_single_page(self, client):
        page_data = [{"OBS_VALUE": str(i)} for i in range(50)]
        mock_http = _make_mock_client()
        mock_http.request = AsyncMock(return_value=_mock_response(200, {"value": page_data}))
        client._client = mock_http

        result = await client._paginated_get("/data360/data", {"DATABASE_ID": "WB_WDI"})
        assert result["success"] is True
        assert result["returned_count"] == 50
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_multi_page(self, client):
        call_count = 0

        async def fake_request(method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            params = kwargs.get("params", {})
            skip = params.get("skip", 0)
            if skip == 0:
                return _mock_response(200, {"value": [{"i": i} for i in range(1000)]})
            elif skip == 1000:
                return _mock_response(200, {"value": [{"i": i} for i in range(500)]})
            return _mock_response(200, {"value": []})

        mock_http = _make_mock_client()
        mock_http.request = AsyncMock(side_effect=fake_request)
        client._client = mock_http

        result = await client._paginated_get("/data360/data", {"DATABASE_ID": "WB_WDI"})
        assert result["success"] is True
        assert result["returned_count"] == 1500
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_truncation_at_max_records(self, client):
        mock_http = _make_mock_client()
        mock_http.request = AsyncMock(
            return_value=_mock_response(200, {"value": [{"i": i} for i in range(1000)]})
        )
        client._client = mock_http

        result = await client._paginated_get("/data360/data", {"DATABASE_ID": "WB_WDI"})
        assert result["success"] is True
        assert result["returned_count"] == 5000
        assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_pagination_error_returns_structured_error(self, client):
        mock_http = _make_mock_client()
        mock_http.request = AsyncMock(return_value=_mock_response(500))
        client._client = mock_http

        # max_retries=3 means 4 attempts total, all 500 -> error
        result = await client._paginated_get("/data360/data", {"DATABASE_ID": "WB_WDI"})
        assert result["success"] is False


# --- Task 4: Public API methods ---


class TestPublicMethods:
    @pytest.mark.asyncio
    async def test_get_maps_params(self, client):
        mock_http = _make_mock_client()
        mock_http.request = AsyncMock(return_value=_mock_response(200, {"value": []}))
        client._client = mock_http

        result = await client.get("/data360/data", database_id="WB_WDI", ref_area="BRA")
        assert result["success"] is True
        assert result["data"] == {"value": []}
        call_kwargs = mock_http.request.call_args
        assert call_kwargs.kwargs["params"] == {"DATABASE_ID": "WB_WDI", "REF_AREA": "BRA"}

    @pytest.mark.asyncio
    async def test_post_maps_body(self, client):
        mock_http = _make_mock_client()
        mock_http.request = AsyncMock(return_value=_mock_response(200, {"results": []}))
        client._client = mock_http

        result = await client.post("/data360/searchv2", search_text="CO2")
        assert result["success"] is True
        assert result["data"] == {"results": []}
        call_kwargs = mock_http.request.call_args
        assert call_kwargs.kwargs["json"] == {"SEARCH_TEXT": "CO2"}

    @pytest.mark.asyncio
    async def test_get_paginated_maps_params(self, client):
        page_data = [{"OBS_VALUE": "1"}]
        mock_http = _make_mock_client()
        mock_http.request = AsyncMock(return_value=_mock_response(200, {"value": page_data}))
        client._client = mock_http

        result = await client.get_paginated("/data360/data", database_id="WB_WDI")
        assert result["success"] is True
        assert result["returned_count"] == 1
