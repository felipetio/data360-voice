"""Tests for MCP server tool definitions."""

import pytest
from unittest.mock import AsyncMock, patch

from mcp_server.server import search_indicators


@pytest.fixture
def mock_client():
    """Provide a patched Data360Client with a mockable .post() method."""
    with patch("mcp_server.server.Data360Client") as MockClient:
        instance = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        yield instance


class TestSearchIndicators:
    """Tests for the search_indicators MCP tool."""

    @pytest.mark.asyncio
    async def test_successful_search(self, mock_client):
        """AC1: Successful search returns correct format with indicator details."""
        mock_client.post = AsyncMock(return_value={
            "success": True,
            "data": {
                "results": [
                    {
                        "indicatorId": "WB_WDI_EN_ATM_CO2E_KT",
                        "name": "CO2 emissions (kt)",
                        "description": "Carbon dioxide emissions from burning fossil fuels.",
                        "topics": ["Climate Change"],
                        "datasetName": "World Development Indicators",
                    }
                ]
            },
        })

        result = await search_indicators(query="CO2 emissions")

        assert result["success"] is True
        assert len(result["data"]) == 1
        assert result["data"][0]["indicatorId"] == "WB_WDI_EN_ATM_CO2E_KT"
        assert result["total_count"] == 1
        assert result["returned_count"] == 1
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_default_parameters(self, mock_client):
        """AC1: Default parameters top=10, skip=0 are passed to client."""
        mock_client.post = AsyncMock(return_value={"success": True, "data": {"results": []}})

        await search_indicators(query="test")

        mock_client.post.assert_called_once_with(
            "/data360/searchv2", search="test", top=10, skip=0
        )

    @pytest.mark.asyncio
    async def test_optional_parameters_forwarded(self, mock_client):
        """AC2: Optional parameters are forwarded to the API."""
        mock_client.post = AsyncMock(return_value={"success": True, "data": {"results": []}})

        await search_indicators(query="CO2", top=5, skip=10, filter="some filter")

        mock_client.post.assert_called_once_with(
            "/data360/searchv2", search="CO2", top=5, skip=10, filter="some filter"
        )

    @pytest.mark.asyncio
    async def test_filter_none_not_forwarded(self, mock_client):
        """AC2: When filter is None (default), it should not be passed to client."""
        mock_client.post = AsyncMock(return_value={"success": True, "data": {"results": []}})

        await search_indicators(query="test", top=10, skip=0)

        mock_client.post.assert_called_once_with(
            "/data360/searchv2", search="test", top=10, skip=0
        )

    @pytest.mark.asyncio
    async def test_empty_results(self, mock_client):
        """AC3: Empty results return correct format."""
        mock_client.post = AsyncMock(return_value={"success": True, "data": {"results": []}})

        result = await search_indicators(query="nonexistent")

        assert result["success"] is True
        assert result["data"] == []
        assert result["total_count"] == 0
        assert result["returned_count"] == 0
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_api_error_passthrough(self, mock_client):
        """AC4: API errors are passed through directly."""
        mock_client.post = AsyncMock(return_value={
            "success": False,
            "error": "Data360 API returned 503 after 3 retries",
            "error_type": "api_error",
        })

        result = await search_indicators(query="test")

        assert result["success"] is False
        assert result["error"] == "Data360 API returned 503 after 3 retries"
        assert result["error_type"] == "api_error"

    @pytest.mark.asyncio
    async def test_timeout_error_passthrough(self, mock_client):
        """AC4: Timeout errors are passed through directly."""
        mock_client.post = AsyncMock(return_value={
            "success": False,
            "error": "Request timed out: TimeoutError",
            "error_type": "timeout",
        })

        result = await search_indicators(query="test")

        assert result["success"] is False
        assert result["error_type"] == "timeout"

    @pytest.mark.asyncio
    async def test_multiple_results(self, mock_client):
        """AC1: Multiple results are all returned with correct counts."""
        results = [
            {"indicatorId": f"IND_{i}", "name": f"Indicator {i}"} for i in range(3)
        ]
        mock_client.post = AsyncMock(return_value={"success": True, "data": {"results": results}})

        result = await search_indicators(query="test")

        assert result["success"] is True
        assert len(result["data"]) == 3
        assert result["total_count"] == 3
        assert result["returned_count"] == 3

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_error(self, mock_client):
        """Architecture: Tool must return dict, never raise exceptions."""
        mock_client.post = AsyncMock(side_effect=RuntimeError("connection exploded"))

        result = await search_indicators(query="test")

        assert result["success"] is False
        assert "connection exploded" in result["error"]
        assert result["error_type"] == "api_error"
