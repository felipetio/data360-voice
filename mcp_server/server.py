"""FastMCP server with Data360 API tools."""

import logging

from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("data360-voice", instructions="World Bank Data360 climate and development data tools.")
