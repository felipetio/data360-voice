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
