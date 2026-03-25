"""Tests for MCP server tool definitions."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from mcp_server.data360_client import Data360Client
from mcp_server.server import get_data, get_disaggregation, get_metadata, list_indicators, search_indicators

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict | list:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def mock_client():
    """Provide a patched shared _client with mockable methods."""
    instance = AsyncMock()
    instance._db_name_cache = {}
    instance.cache_db_names = Data360Client.cache_db_names.__get__(instance)
    instance.enrich_citation_source = AsyncMock()
    # Preserve real _map_params so param mapping tests work correctly
    instance._map_params = Data360Client._map_params
    with patch("mcp_server.server._client", instance):
        yield instance


class TestSearchIndicators:
    """Tests for the search_indicators MCP tool."""

    @pytest.mark.asyncio
    async def test_successful_search(self, mock_client):
        """AC1: Successful search returns correct format with real API structure."""
        fixture = _load_fixture("searchv2_response.json")
        mock_client._request = AsyncMock(return_value=fixture)

        result = await search_indicators(query="CO2 emissions")

        assert result["success"] is True
        assert len(result["data"]) == 2
        assert result["data"][0]["id"] == "META_WB_SSGD_CO2_EMISSIONS"
        assert result["data"][0]["series_description"]["name"] == "CO2 emissions"
        assert result["total_count"] == 300
        assert result["returned_count"] == 2
        assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_default_parameters(self, mock_client):
        """AC1: Default parameters top=10, skip=0, count=True are passed to client."""
        mock_client._request = AsyncMock(return_value={"value": [], "@odata.count": 0})

        await search_indicators(query="test")

        mock_client._request.assert_called_once_with(
            "POST",
            "/data360/searchv2",
            json_body={"search": "test", "top": 10, "skip": 0, "count": True},
        )

    @pytest.mark.asyncio
    async def test_optional_parameters_forwarded(self, mock_client):
        """AC2: Optional parameters are forwarded to the API."""
        mock_client._request = AsyncMock(return_value={"value": [], "@odata.count": 0})

        await search_indicators(query="CO2", top=5, skip=10, filter="some filter")

        mock_client._request.assert_called_once_with(
            "POST",
            "/data360/searchv2",
            json_body={"search": "CO2", "top": 5, "skip": 10, "count": True, "filter": "some filter"},
        )

    @pytest.mark.asyncio
    async def test_filter_none_not_forwarded(self, mock_client):
        """AC2: When filter is None (default), it should not be passed to client."""
        mock_client._request = AsyncMock(return_value={"value": [], "@odata.count": 0})

        await search_indicators(query="test", top=10, skip=0)

        mock_client._request.assert_called_once_with(
            "POST",
            "/data360/searchv2",
            json_body={"search": "test", "top": 10, "skip": 0, "count": True},
        )

    @pytest.mark.asyncio
    async def test_empty_results(self, mock_client):
        """AC3: Empty results return correct format."""
        mock_client._request = AsyncMock(return_value={"value": [], "@odata.count": 0})

        result = await search_indicators(query="nonexistent")

        assert result["success"] is True
        assert result["data"] == []
        assert result["total_count"] == 0
        assert result["returned_count"] == 0
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_api_error_passthrough(self, mock_client):
        """AC4: API errors are passed through directly."""
        mock_client._request = AsyncMock(
            return_value={
                "success": False,
                "error": "Data360 API returned 503 after 3 retries",
                "error_type": "api_error",
            }
        )

        result = await search_indicators(query="test")

        assert result["success"] is False
        assert result["error"] == "Data360 API returned 503 after 3 retries"
        assert result["error_type"] == "api_error"

    @pytest.mark.asyncio
    async def test_timeout_error_passthrough(self, mock_client):
        """AC4: Timeout errors are passed through directly."""
        mock_client._request = AsyncMock(
            return_value={
                "success": False,
                "error": "Request timed out: TimeoutError",
                "error_type": "timeout",
            }
        )

        result = await search_indicators(query="test")

        assert result["success"] is False
        assert result["error_type"] == "timeout"

    @pytest.mark.asyncio
    async def test_total_count_from_odata(self, mock_client):
        """AC1: total_count comes from @odata.count, not len(results)."""
        mock_client._request = AsyncMock(
            return_value={
                "@odata.count": 150,
                "value": [{"id": f"IND_{i}"} for i in range(10)],
            }
        )

        result = await search_indicators(query="test", top=10)

        assert result["success"] is True
        assert result["total_count"] == 150
        assert result["returned_count"] == 10
        assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_not_truncated_when_all_returned(self, mock_client):
        """AC1: truncated is False when returned_count equals total_count."""
        mock_client._request = AsyncMock(
            return_value={
                "@odata.count": 3,
                "value": [{"id": f"IND_{i}"} for i in range(3)],
            }
        )

        result = await search_indicators(query="test")

        assert result["truncated"] is False
        assert result["total_count"] == 3
        assert result["returned_count"] == 3

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_error(self, mock_client):
        """Architecture: Tool must return dict, never raise exceptions."""
        mock_client._request = AsyncMock(side_effect=RuntimeError("connection exploded"))

        result = await search_indicators(query="test")

        assert result["success"] is False
        assert "connection exploded" in result["error"]
        assert result["error_type"] == "api_error"

    @pytest.mark.asyncio
    async def test_populates_db_name_cache(self, mock_client):
        """search_indicators populates the database name cache from results."""
        fixture = _load_fixture("searchv2_response.json")
        mock_client._request = AsyncMock(return_value=fixture)

        await search_indicators(query="CO2 emissions")

        assert mock_client._db_name_cache["WB_SSGD"] == "Social sustainability global database"
        assert mock_client._db_name_cache["OWID_CB"] == "CO2 and Greenhouse Gas Emissions"


class TestGetData:
    """Tests for the get_data MCP tool."""

    @pytest.mark.asyncio
    async def test_successful_data_retrieval(self, mock_client):
        """AC1: Successful retrieval returns data with preserved API field names."""
        fixture = _load_fixture("data_response.json")
        mock_client._paginated_get = AsyncMock(
            return_value={
                "success": True,
                "data": fixture["value"],
                "total_count": fixture["count"],
                "returned_count": fixture["count"],
                "truncated": False,
            }
        )

        result = await get_data(database_id="WB_SSGD", indicator="WB_SSGD_CO2_EMISSIONS", ref_area="BRA")

        assert result["success"] is True
        assert len(result["data"]) == 2
        record = result["data"][0]
        assert record["OBS_VALUE"] == "2.06426"
        assert record["DATABASE_ID"] == "WB_SSGD"
        assert record["TIME_PERIOD"] == "2018"
        assert record["INDICATOR"] == "WB_SSGD_CO2_EMISSIONS"
        assert record["LATEST_DATA"] is False
        assert result["data"][1]["LATEST_DATA"] is True
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_required_parameters_mapped_to_uppercase(self, mock_client):
        """AC1: Required parameters are mapped to UPPERCASE via _paginated_get."""
        mock_client._paginated_get = AsyncMock(
            return_value={
                "success": True,
                "data": [],
                "total_count": 0,
                "returned_count": 0,
                "truncated": False,
            }
        )

        await get_data(database_id="WB_WDI", indicator="WB_WDI_EN_ATM_CO2E_KT")

        mock_client._paginated_get.assert_called_once_with(
            "/data360/data", {"DATABASE_ID": "WB_WDI", "INDICATOR": "WB_WDI_EN_ATM_CO2E_KT"}
        )

    @pytest.mark.asyncio
    async def test_optional_ref_area_mapped_to_uppercase(self, mock_client):
        """AC1: Optional ref_area is mapped to UPPERCASE."""
        mock_client._paginated_get = AsyncMock(
            return_value={
                "success": True,
                "data": [],
                "total_count": 0,
                "returned_count": 0,
                "truncated": False,
            }
        )

        await get_data(database_id="WB_WDI", indicator="IND", ref_area="BRA")

        mock_client._paginated_get.assert_called_once_with(
            "/data360/data", {"DATABASE_ID": "WB_WDI", "INDICATOR": "IND", "REF_AREA": "BRA"}
        )

    @pytest.mark.asyncio
    async def test_time_period_params_camel_case(self, mock_client):
        """AC2: Time period params use camelCase (timePeriodFrom, timePeriodTo)."""
        mock_client._paginated_get = AsyncMock(
            return_value={
                "success": True,
                "data": [],
                "total_count": 0,
                "returned_count": 0,
                "truncated": False,
            }
        )

        await get_data(
            database_id="WB_WDI",
            indicator="IND",
            time_period_from="2015",
            time_period_to="2023",
        )

        mock_client._paginated_get.assert_called_once_with(
            "/data360/data",
            {"DATABASE_ID": "WB_WDI", "INDICATOR": "IND", "timePeriodFrom": "2015", "timePeriodTo": "2023"},
        )

    @pytest.mark.asyncio
    async def test_none_optional_params_excluded(self, mock_client):
        """AC2: None optional params are not included in the params dict."""
        mock_client._paginated_get = AsyncMock(
            return_value={
                "success": True,
                "data": [],
                "total_count": 0,
                "returned_count": 0,
                "truncated": False,
            }
        )

        await get_data(database_id="WB_WDI", indicator="IND")

        mock_client._paginated_get.assert_called_once_with(
            "/data360/data", {"DATABASE_ID": "WB_WDI", "INDICATOR": "IND"}
        )

    @pytest.mark.asyncio
    async def test_paginated_response_passthrough(self, mock_client):
        """AC3: Paginated response with truncation is passed through."""
        mock_client._paginated_get = AsyncMock(
            return_value={
                "success": True,
                "data": [{"OBS_VALUE": str(i)} for i in range(5000)],
                "total_count": 5000,
                "returned_count": 5000,
                "truncated": True,
            }
        )

        result = await get_data(database_id="WB_WDI", indicator="IND")

        assert result["success"] is True
        assert result["total_count"] == 5000
        assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_empty_results(self, mock_client):
        """AC4: No data returns correct empty format."""
        mock_client._paginated_get = AsyncMock(
            return_value={
                "success": True,
                "data": [],
                "total_count": 0,
                "returned_count": 0,
                "truncated": False,
            }
        )

        result = await get_data(database_id="WB_WDI", indicator="IND", ref_area="XYZ")

        assert result["success"] is True
        assert result["data"] == []
        assert result["total_count"] == 0
        assert result["returned_count"] == 0
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_api_error_passthrough(self, mock_client):
        """AC4: API errors are passed through."""
        mock_client._paginated_get = AsyncMock(
            return_value={
                "success": False,
                "error": "Data360 API returned 500 after 3 retries",
                "error_type": "api_error",
            }
        )

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

    @pytest.mark.asyncio
    async def test_calls_enrich_citation_source(self, mock_client):
        """get_data calls enrich_citation_source on successful results."""
        data = [{"OBS_VALUE": "1", "DATABASE_ID": "WB_SSGD"}]
        mock_client._paginated_get = AsyncMock(
            return_value={
                "success": True,
                "data": data,
                "total_count": 1,
                "returned_count": 1,
                "truncated": False,
            }
        )

        await get_data(database_id="WB_SSGD", indicator="IND")

        mock_client.enrich_citation_source.assert_called_once_with(data)

    @pytest.mark.asyncio
    async def test_skips_enrich_on_empty_data(self, mock_client):
        """get_data does not call enrich_citation_source when data is empty."""
        mock_client._paginated_get = AsyncMock(
            return_value={
                "success": True,
                "data": [],
                "total_count": 0,
                "returned_count": 0,
                "truncated": False,
            }
        )

        await get_data(database_id="WB_WDI", indicator="IND")

        mock_client.enrich_citation_source.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_enrich_on_error(self, mock_client):
        """get_data does not call enrich_citation_source on API error."""
        mock_client._paginated_get = AsyncMock(
            return_value={
                "success": False,
                "error": "fail",
                "error_type": "api_error",
            }
        )

        await get_data(database_id="WB_WDI", indicator="IND")

        mock_client.enrich_citation_source.assert_not_called()


class TestGetMetadata:
    """Tests for the get_metadata MCP tool."""

    @pytest.mark.asyncio
    async def test_successful_metadata_retrieval(self, mock_client):
        """AC1: Successful retrieval returns metadata with real API structure."""
        fixture = _load_fixture("metadata_response.json")
        mock_client._request = AsyncMock(return_value=fixture)

        result = await get_metadata(query="&$filter=series_description/idno eq 'WB_WDI_SP_POP_TOTL'")

        assert result["success"] is True
        assert len(result["data"]) == 1
        item = result["data"][0]
        assert item["id"] == "META_WB_WDI_SP_POP_TOTL"
        assert item["series_description"]["idno"] == "WB_WDI_SP_POP_TOTL"
        assert item["series_description"]["database_name"] == "World Development Indicators (WDI)"
        assert result["total_count"] == 1
        assert result["returned_count"] == 1
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_query_passed_as_body(self, mock_client):
        """AC1: Query string is passed as JSON body 'query' field."""
        mock_client._request = AsyncMock(return_value={"value": [], "@odata.count": 0})

        await get_metadata(query="&$filter=series_description/database_id eq 'WB_WDI'")

        mock_client._request.assert_called_once_with(
            "POST",
            "/data360/metadata",
            json_body={"query": "&$filter=series_description/database_id eq 'WB_WDI'"},
        )

    @pytest.mark.asyncio
    async def test_total_count_from_odata(self, mock_client):
        """AC1: total_count comes from @odata.count."""
        mock_client._request = AsyncMock(
            return_value={
                "@odata.count": 50,
                "value": [{"id": "META_1"}],
            }
        )

        result = await get_metadata(query="&$filter=series_description/database_id eq 'WB_WDI'&$top=1")

        assert result["total_count"] == 50
        assert result["returned_count"] == 1
        assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_empty_results(self, mock_client):
        """AC1: Empty results return correct format."""
        mock_client._request = AsyncMock(return_value={"value": [], "@odata.count": 0})

        result = await get_metadata(query="&$filter=series_description/idno eq 'NONEXISTENT'")

        assert result["success"] is True
        assert result["data"] == []
        assert result["total_count"] == 0
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_api_error_passthrough(self, mock_client):
        """AC4: API errors are passed through."""
        mock_client._request = AsyncMock(
            return_value={
                "success": False,
                "error": "Data360 API returned 500 after 3 retries",
                "error_type": "api_error",
            }
        )

        result = await get_metadata(query="&$filter=bad")

        assert result["success"] is False
        assert result["error_type"] == "api_error"

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_error(self, mock_client):
        """AC4: Tool must return dict, never raise."""
        mock_client._request = AsyncMock(side_effect=RuntimeError("boom"))

        result = await get_metadata(query="test")

        assert result["success"] is False
        assert "boom" in result["error"]
        assert result["error_type"] == "api_error"


class TestListIndicators:
    """Tests for the list_indicators MCP tool."""

    @pytest.mark.asyncio
    async def test_successful_list(self, mock_client):
        """AC2: Successful list returns indicator IDs from real API."""
        fixture = _load_fixture("indicators_response.json")
        mock_client._request = AsyncMock(return_value=fixture)

        result = await list_indicators(dataset_id="WB_WDI")

        assert result["success"] is True
        assert len(result["data"]) == 5
        assert "WB_WDI_SP_POP_TOTL" in result["data"]
        assert result["total_count"] == 5
        assert result["returned_count"] == 5
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_camel_case_param(self, mock_client):
        """AC2: dataset_id is passed as camelCase datasetId."""
        mock_client._request = AsyncMock(return_value=[])

        await list_indicators(dataset_id="WB_WDI")

        mock_client._request.assert_called_once_with(
            "GET",
            "/data360/indicators",
            params={"datasetId": "WB_WDI"},
        )

    @pytest.mark.asyncio
    async def test_empty_results(self, mock_client):
        """AC2: Empty dataset returns correct format."""
        mock_client._request = AsyncMock(return_value=[])

        result = await list_indicators(dataset_id="NONEXISTENT")

        assert result["success"] is True
        assert result["data"] == []
        assert result["total_count"] == 0
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_api_error_passthrough(self, mock_client):
        """AC4: API errors are passed through."""
        mock_client._request = AsyncMock(
            return_value={
                "success": False,
                "error": "Data360 API returned 404: Not Found",
                "error_type": "api_error",
            }
        )

        result = await list_indicators(dataset_id="BAD")

        assert result["success"] is False
        assert result["error_type"] == "api_error"

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_error(self, mock_client):
        """AC4: Tool must return dict, never raise."""
        mock_client._request = AsyncMock(side_effect=RuntimeError("boom"))

        result = await list_indicators(dataset_id="WB_WDI")

        assert result["success"] is False
        assert "boom" in result["error"]
        assert result["error_type"] == "api_error"


class TestGetDisaggregation:
    """Tests for the get_disaggregation MCP tool."""

    @pytest.mark.asyncio
    async def test_successful_disaggregation(self, mock_client):
        """AC3: Successful retrieval returns dimension objects from real API."""
        fixture = _load_fixture("disaggregation_response.json")
        mock_client._request = AsyncMock(return_value=fixture)

        result = await get_disaggregation(dataset_id="WB_WDI", indicator_id="WB_WDI_SP_POP_TOTL")

        assert result["success"] is True
        assert len(result["data"]) == 6
        freq = result["data"][0]
        assert freq["field_name"] == "FREQ"
        assert freq["field_value"] == ["A"]
        ref_area = result["data"][1]
        assert ref_area["field_name"] == "REF_AREA"
        assert "ABW" in ref_area["field_value"]
        assert result["total_count"] == 6
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_required_and_optional_params(self, mock_client):
        """AC3: Both datasetId and indicatorId passed as camelCase."""
        mock_client._request = AsyncMock(return_value=[])

        await get_disaggregation(dataset_id="WB_WDI", indicator_id="WB_WDI_SP_POP_TOTL")

        mock_client._request.assert_called_once_with(
            "GET",
            "/data360/disaggregation",
            params={"datasetId": "WB_WDI", "indicatorId": "WB_WDI_SP_POP_TOTL"},
        )

    @pytest.mark.asyncio
    async def test_indicator_id_none_not_included(self, mock_client):
        """AC3: When indicator_id is None, only datasetId is passed."""
        mock_client._request = AsyncMock(return_value=[])

        await get_disaggregation(dataset_id="WB_WDI")

        mock_client._request.assert_called_once_with(
            "GET",
            "/data360/disaggregation",
            params={"datasetId": "WB_WDI"},
        )

    @pytest.mark.asyncio
    async def test_empty_results(self, mock_client):
        """AC3: No dimensions returns correct format."""
        mock_client._request = AsyncMock(return_value=[])

        result = await get_disaggregation(dataset_id="NONEXISTENT")

        assert result["success"] is True
        assert result["data"] == []
        assert result["total_count"] == 0
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_api_error_passthrough(self, mock_client):
        """AC4: API errors are passed through."""
        mock_client._request = AsyncMock(
            return_value={
                "success": False,
                "error": "Data360 API returned 500 after 3 retries",
                "error_type": "api_error",
            }
        )

        result = await get_disaggregation(dataset_id="WB_WDI")

        assert result["success"] is False
        assert result["error_type"] == "api_error"

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_error(self, mock_client):
        """AC4: Tool must return dict, never raise."""
        mock_client._request = AsyncMock(side_effect=RuntimeError("boom"))

        result = await get_disaggregation(dataset_id="WB_WDI")

        assert result["success"] is False
        assert "boom" in result["error"]
        assert result["error_type"] == "api_error"
