"""MCP Server configuration settings."""

import os

BASE_URL = os.getenv("DATA360_BASE_URL", "https://data360api.worldbank.org")

# HTTP client settings
REQUEST_TIMEOUT = int(os.getenv("DATA360_REQUEST_TIMEOUT", "30"))
MAX_RETRIES = int(os.getenv("DATA360_MAX_RETRIES", "3"))
RETRY_BACKOFF_BASE = float(os.getenv("DATA360_RETRY_BACKOFF_BASE", "1.0"))

# Pagination settings
PAGE_SIZE = 1000  # Max records per API call
MAX_RECORDS = 5000  # Hard cap per tool call
