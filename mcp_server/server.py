"""FastMCP server with Data360 API tools."""

import logging
from typing import Any

from fastmcp import FastMCP

from mcp_server.data360_client import Data360Client

logger = logging.getLogger(__name__)

mcp = FastMCP("data360-voice", instructions="World Bank Data360 climate and development data tools.")

_client = Data360Client()


@mcp.tool()
async def search_indicators(
    query: str,
    top: int = 10,
    skip: int = 0,
    filter: str | None = None,
) -> dict[str, Any]:
    """Search for World Bank Data360 indicators using natural language.

    Args:
        query: Natural language search text (e.g. "drought Brazil", "CO2 emissions").
        top: Maximum number of results to return (default 10).
        skip: Number of results to skip for pagination (default 0).
        filter: Optional OData filter expression.

    Returns:
        Dict with success status, data list, total_count, returned_count, and truncated flag.
    """
    try:
        body: dict[str, Any] = {"search": query, "top": top, "skip": skip, "count": True}
        if filter is not None:
            body["filter"] = filter

        response = await _client._request("POST", "/data360/searchv2", json_body=body)

        if isinstance(response, dict) and response.get("success") is False:
            return response

        results = response.get("value", [])
        _client.cache_db_names(results)
        total_count = response.get("@odata.count") or len(results)
        returned_count = len(results)
        return {
            "success": True,
            "data": results,
            "total_count": total_count,
            "returned_count": returned_count,
            "truncated": total_count > returned_count,
        }
    except Exception as exc:
        logger.error("search_indicators failed: %s", exc)
        return {"success": False, "error": str(exc), "error_type": "api_error"}


@mcp.tool()
async def get_data(
    database_id: str,
    indicator: str,
    ref_area: str | None = None,
    time_period_from: str | None = None,
    time_period_to: str | None = None,
) -> dict[str, Any]:
    """Retrieve data values for a specific indicator by country and time period.

    Args:
        database_id: Dataset identifier (e.g. "WB_WDI").
        indicator: Indicator code (e.g. "WB_WDI_EN_ATM_CO2E_KT").
        ref_area: Country/region code (e.g. "BRA"). Optional.
        time_period_from: Start year filter (e.g. "2015"). Optional.
        time_period_to: End year filter (e.g. "2023"). Optional.

    Returns:
        Dict with success status, data list preserving API field names
        (OBS_VALUE, DATA_SOURCE, TIME_PERIOD, etc.), total_count, returned_count,
        and truncated flag.
    """
    try:
        # Standard params go through _map_params (snake_case -> UPPERCASE)
        kwargs: dict[str, Any] = {"database_id": database_id, "indicator": indicator}
        if ref_area is not None:
            kwargs["ref_area"] = ref_area

        # Map standard params to UPPERCASE, then add camelCase time period
        # params directly (API expects timePeriodFrom, not TIME_PERIOD_FROM)
        params = Data360Client._map_params(kwargs)
        if time_period_from is not None:
            params["timePeriodFrom"] = time_period_from
        if time_period_to is not None:
            params["timePeriodTo"] = time_period_to
        result = await _client._paginated_get("/data360/data", params)
        if result.get("success") and result.get("data"):
            await _client.enrich_citation_source(result["data"])
        return result
    except Exception as exc:
        logger.error("get_data failed: %s", exc)
        return {"success": False, "error": str(exc), "error_type": "api_error"}


@mcp.tool()
async def get_metadata(
    query: str,
) -> dict[str, Any]:
    """Get detailed metadata about indicators, datasets, and topics.

    Args:
        query: OData query string (e.g. "&$filter=series_description/idno eq 'WB_WDI_SP_POP_TOTL'").
            Supports $filter, $select, and $top OData parameters.

    Returns:
        Dict with success status, data list of metadata items, total_count,
        returned_count, and truncated flag.
    """
    try:
        body: dict[str, Any] = {"query": query}

        response = await _client._request("POST", "/data360/metadata", json_body=body)

        if isinstance(response, dict) and response.get("success") is False:
            return response

        if not isinstance(response, dict):
            logger.warning("get_metadata: unexpected response type %s", type(response).__name__)
            return {"success": True, "data": [], "total_count": 0, "returned_count": 0, "truncated": False}

        results = response.get("value", [])
        total_count = response.get("@odata.count") or len(results)
        returned_count = len(results)
        return {
            "success": True,
            "data": results,
            "total_count": total_count,
            "returned_count": returned_count,
            "truncated": total_count > returned_count,
        }
    except Exception as exc:
        logger.error("get_metadata failed: %s", exc)
        return {"success": False, "error": str(exc), "error_type": "api_error"}


@mcp.tool()
async def list_indicators(
    dataset_id: str,
) -> dict[str, Any]:
    """List all available indicators in a given dataset.

    Args:
        dataset_id: Dataset identifier (e.g. "WB_WDI").

    Returns:
        Dict with success status, data list of indicator ID strings,
        total_count, returned_count, and truncated flag.
    """
    try:
        params: dict[str, Any] = {"datasetId": dataset_id}

        response = await _client._request("GET", "/data360/indicators", params=params)

        if isinstance(response, dict) and response.get("success") is False:
            return response

        if not isinstance(response, list):
            logger.warning("list_indicators: unexpected response type %s", type(response).__name__)

        results = response if isinstance(response, list) else []
        return {
            "success": True,
            "data": results,
            "total_count": len(results),
            "returned_count": len(results),
            "truncated": False,
        }
    except Exception as exc:
        logger.error("list_indicators failed: %s", exc)
        return {"success": False, "error": str(exc), "error_type": "api_error"}


@mcp.tool()
async def get_disaggregation(
    dataset_id: str,
    indicator_id: str | None = None,
) -> dict[str, Any]:
    """Get available disaggregation dimensions for a dataset or indicator.

    Args:
        dataset_id: Dataset identifier (e.g. "WB_WDI").
        indicator_id: Indicator code (e.g. "WB_WDI_SP_POP_TOTL"). Optional.

    Returns:
        Dict with success status, data list of dimension objects
        (field_name, label_name, field_value), total_count, returned_count,
        and truncated flag.
    """
    try:
        params: dict[str, Any] = {"datasetId": dataset_id}
        if indicator_id is not None:
            params["indicatorId"] = indicator_id

        response = await _client._request("GET", "/data360/disaggregation", params=params)

        if isinstance(response, dict) and response.get("success") is False:
            return response

        if not isinstance(response, list):
            logger.warning("get_disaggregation: unexpected response type %s", type(response).__name__)

        results = response if isinstance(response, list) else []
        return {
            "success": True,
            "data": results,
            "total_count": len(results),
            "returned_count": len(results),
            "truncated": False,
        }
    except Exception as exc:
        logger.error("get_disaggregation failed: %s", exc)
        return {"success": False, "error": str(exc), "error_type": "api_error"}
