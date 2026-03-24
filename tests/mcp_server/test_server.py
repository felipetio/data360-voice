"""Tests for MCP server tool definitions."""

import pytest
from unittest.mock import AsyncMock, patch

from mcp_server.data360_client import Data360Client
from mcp_server.server import search_indicators, get_data


@pytest.fixture
def mock_client():
    """Provide a patched Data360Client with mockable methods."""
    with patch("mcp_server.server.Data360Client") as MockClient:
        instance = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        # Preserve real _map_params so param mapping tests work correctly
        MockClient._map_params = Data360Client._map_params
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


class TestGetData:
    """Tests for the get_data MCP tool."""

    @pytest.mark.asyncio
    async def test_successful_data_retrieval(self, mock_client):
        """AC1: Successful retrieval returns data with preserved API field names."""
        mock_client._paginated_get = AsyncMock(return_value={
            "success": True,
            "data": [
                {
                    "DATABASE_ID": "WB_WDI",
                    "INDICATOR": "EN_ATM_CO2E_KT",
                    "REF_AREA": "BRA",
                    "TIME_PERIOD": "2020",
                    "OBS_VALUE": "408645.8",
                    "DATA_SOURCE": "World Development Indicators",
                    "COMMENT_TS": "CO2 emissions (kt)",
                    "LATEST_DATA": True,
                }
            ],
            "total_count": 1,
            "returned_count": 1,
            "truncated": False,
        })

        result = await get_data(database_id="WB_WDI", indicator="WB_WDI_EN_ATM_CO2E_KT", ref_area="BRA")

        assert result["success"] is True
        assert len(result["data"]) == 1
        record = result["data"][0]
        assert record["OBS_VALUE"] == "408645.8"
        assert record["DATA_SOURCE"] == "World Development Indicators"
        assert record["TIME_PERIOD"] == "2020"
        assert record["COMMENT_TS"] == "CO2 emissions (kt)"
        assert record["LATEST_DATA"] is True
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_required_parameters_mapped_to_uppercase(self, mock_client):
        """AC1: Required parameters are mapped to UPPERCASE via _paginated_get."""
        mock_client._paginated_get = AsyncMock(return_value={
            "success": True, "data": [], "total_count": 0, "returned_count": 0, "truncated": False,
        })

        await get_data(database_id="WB_WDI", indicator="WB_WDI_EN_ATM_CO2E_KT")

        mock_client._paginated_get.assert_called_once_with(
            "/data360/data", {"DATABASE_ID": "WB_WDI", "INDICATOR": "WB_WDI_EN_ATM_CO2E_KT"}
        )

    @pytest.mark.asyncio
    async def test_optional_ref_area_mapped_to_uppercase(self, mock_client):
        """AC1: Optional ref_area is mapped to UPPERCASE."""
        mock_client._paginated_get = AsyncMock(return_value={
            "success": True, "data": [], "total_count": 0, "returned_count": 0, "truncated": False,
        })

        await get_data(database_id="WB_WDI", indicator="IND", ref_area="BRA")

        mock_client._paginated_get.assert_called_once_with(
            "/data360/data", {"DATABASE_ID": "WB_WDI", "INDICATOR": "IND", "REF_AREA": "BRA"}
        )

    @pytest.mark.asyncio
    async def test_time_period_params_camel_case(self, mock_client):
        """AC2: Time period params use camelCase (timePeriodFrom, timePeriodTo)."""
        mock_client._paginated_get = AsyncMock(return_value={
            "success": True, "data": [], "total_count": 0, "returned_count": 0, "truncated": False,
        })

        await get_data(
            database_id="WB_WDI", indicator="IND",
            time_period_from="2015", time_period_to="2023",
        )

        mock_client._paginated_get.assert_called_once_with(
            "/data360/data",
            {"DATABASE_ID": "WB_WDI", "INDICATOR": "IND",
             "timePeriodFrom": "2015", "timePeriodTo": "2023"},
        )

    @pytest.mark.asyncio
    async def test_none_optional_params_excluded(self, mock_client):
        """AC2: None optional params are not included in the params dict."""
        mock_client._paginated_get = AsyncMock(return_value={
            "success": True, "data": [], "total_count": 0, "returned_count": 0, "truncated": False,
        })

        await get_data(database_id="WB_WDI", indicator="IND")

        mock_client._paginated_get.assert_called_once_with(
            "/data360/data", {"DATABASE_ID": "WB_WDI", "INDICATOR": "IND"}
        )

    @pytest.mark.asyncio
    async def test_paginated_response_passthrough(self, mock_client):
        """AC3: Paginated response with truncation is passed through."""
        mock_client._paginated_get = AsyncMock(return_value={
            "success": True,
            "data": [{"OBS_VALUE": str(i)} for i in range(5000)],
            "total_count": 5000,
            "returned_count": 5000,
            "truncated": True,
        })

        result = await get_data(database_id="WB_WDI", indicator="IND")

        assert result["success"] is True
        assert result["total_count"] == 5000
        assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_empty_results(self, mock_client):
        """AC4: No data returns correct empty format."""
        mock_client._paginated_get = AsyncMock(return_value={
            "success": True, "data": [], "total_count": 0, "returned_count": 0, "truncated": False,
        })

        result = await get_data(database_id="WB_WDI", indicator="IND", ref_area="XYZ")

        assert result["success"] is True
        assert result["data"] == []
        assert result["total_count"] == 0
        assert result["returned_count"] == 0
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_api_error_passthrough(self, mock_client):
        """AC4: API errors are passed through."""
        mock_client._paginated_get = AsyncMock(return_value={
            "success": False,
            "error": "Data360 API returned 500 after 3 retries",
            "error_type": "api_error",
        })

        result = await get_data(database_id="WB_WDI", indicator="IND")

        assert result["success"] is False
        assert result["error_type"] == "api_error"

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_error(self, mock_client):
        """Architecture: Tool must return dict, never raise."""
        mock_client._paginated_get = AsyncMock(side_effect=RuntimeError("boom"))

        result = await get_data(database_id="WB_WDI", indicator="IND")

        assert result["success"] is False
        assert "boom" in result["error"]
        assert result["error_type"] == "api_error"
