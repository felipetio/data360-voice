"""FastMCP server with Data360 API tools."""

import logging
from typing import Any

from fastmcp import FastMCP

from mcp_server.data360_client import Data360Client

logger = logging.getLogger(__name__)

mcp = FastMCP("data360-voice", instructions="World Bank Data360 climate and development data tools.")


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
        kwargs: dict[str, Any] = {"search": query, "top": top, "skip": skip}
        if filter is not None:
            kwargs["filter"] = filter

        async with Data360Client() as client:
            response = await client.post("/data360/searchv2", **kwargs)

        if not response.get("success", False):
            return response

        results = response.get("data", {}).get("results", [])
        return {
            "success": True,
            "data": results,
            "total_count": len(results),
            "returned_count": len(results),
            "truncated": False,
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

        async with Data360Client() as client:
            # Map standard params to UPPERCASE, then add camelCase time period
            # params directly (API expects timePeriodFrom, not TIME_PERIOD_FROM)
            params = Data360Client._map_params(kwargs)
            if time_period_from is not None:
                params["timePeriodFrom"] = time_period_from
            if time_period_to is not None:
                params["timePeriodTo"] = time_period_to
            return await client._paginated_get("/data360/data", params)
    except Exception as exc:
        logger.error("get_data failed: %s", exc)
        return {"success": False, "error": str(exc), "error_type": "api_error"}
