"""Async HTTP client for the World Bank Data360 API."""

import asyncio
import logging
import re
from typing import Any

import httpx

from mcp_server.config import (
    BASE_URL,
    MAX_RECORDS,
    MAX_RETRIES,
    PAGE_SIZE,
    REQUEST_TIMEOUT,
    RETRY_BACKOFF_BASE,
)

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class Data360Client:
    """Async client for the World Bank Data360 API.

    Handles parameter mapping (snake_case -> UPPERCASE),
    auto-pagination, retry with exponential backoff, and
    structured error responses.
    """

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = REQUEST_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        retry_backoff_base: float = RETRY_BACKOFF_BASE,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff_base = retry_backoff_base
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()
        self._db_name_cache: dict[str, str] = {}

    @staticmethod
    def _map_params(params: dict) -> dict:
        """Map snake_case parameter names to UPPERCASE for the Data360 API."""
        return {k.upper(): v for k, v in params.items() if v is not None}

    async def _get_client(self) -> httpx.AsyncClient:
        async with self._lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Execute an HTTP request with retry on transient errors.

        Returns parsed JSON on success (dict or list depending on endpoint),
        or a structured error dict on failure.
        """
        url = f"{self.base_url}{endpoint}"
        client = await self._get_client()

        for attempt in range(self.max_retries + 1):
            try:
                logger.debug("Request %s %s params=%s json=%s", method, url, params, json_body)
                kwargs: dict[str, Any] = {}
                if params:
                    kwargs["params"] = params
                if json_body:
                    kwargs["json"] = json_body
                response = await client.request(method, url, **kwargs)

                if response.status_code < 400:
                    try:
                        data = response.json()
                    except ValueError as exc:
                        logger.error("Invalid JSON from %s %s: %s", method, url, exc)
                        return {"success": False, "error": f"Invalid JSON response: {exc}", "error_type": "api_error"}
                    logger.debug("Response %s %s -> %d", method, url, response.status_code)
                    return data

                if response.status_code in _RETRYABLE_STATUS:
                    if attempt < self.max_retries:
                        delay = self.retry_backoff_base * (2**attempt)
                        logger.warning(
                            "Retryable error %d from %s, attempt %d/%d, retrying in %.1fs",
                            response.status_code, url, attempt + 1, self.max_retries, delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    error_msg = f"Data360 API returned {response.status_code} after {self.max_retries} retries"
                    logger.error(error_msg)
                    return {"success": False, "error": error_msg, "error_type": "api_error"}

                error_msg = f"Data360 API returned {response.status_code}: {response.reason_phrase or 'Unknown'}"
                logger.error(error_msg)
                return {"success": False, "error": error_msg, "error_type": "api_error"}

            except httpx.TimeoutException as exc:
                logger.error("Timeout on %s %s: %s", method, url, exc)
                return {"success": False, "error": f"Request timed out: {exc}", "error_type": "timeout"}
            except httpx.RequestError as exc:
                logger.error("Network error on %s %s: %s", method, url, exc)
                return {"success": False, "error": f"Network error: {exc}", "error_type": "api_error"}

    async def _paginated_get(
        self,
        endpoint: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Fetch data with auto-pagination using the skip parameter."""
        all_records: list[dict] = []
        api_total: int | None = None
        skip = 0

        while len(all_records) < MAX_RECORDS:
            page_params = {**params, "skip": skip}
            result = await self._request("GET", endpoint, params=page_params)

            if isinstance(result, dict) and result.get("success") is False:
                return result

            if api_total is None and isinstance(result, dict):
                api_total = result.get("count")

            page_data = result.get("value", [])
            if not page_data:
                break

            all_records.extend(page_data)

            if len(page_data) < PAGE_SIZE or len(all_records) >= MAX_RECORDS:
                break

            skip += PAGE_SIZE

        truncated = len(all_records) >= MAX_RECORDS
        if truncated:
            all_records = all_records[:MAX_RECORDS]

        return {
            "success": True,
            "data": all_records,
            "total_count": api_total if api_total is not None else len(all_records),
            "returned_count": len(all_records),
            "truncated": truncated,
        }

    async def get(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Single GET request with snake_case -> UPPERCASE param mapping."""
        params = self._map_params(kwargs)
        result = await self._request("GET", endpoint, params=params)
        if isinstance(result, dict) and result.get("success") is False:
            return result
        return {"success": True, "data": result}

    async def post(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Single POST request with snake_case -> UPPERCASE body mapping."""
        body = self._map_params(kwargs)
        result = await self._request("POST", endpoint, json_body=body)
        if isinstance(result, dict) and result.get("success") is False:
            return result
        return {"success": True, "data": result}

    async def get_paginated(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Paginated GET request with snake_case -> UPPERCASE param mapping."""
        params = self._map_params(kwargs)
        return await self._paginated_get(endpoint, params)

    def cache_db_names(self, results: list[dict]) -> None:
        """Extract database_id/database_name from search results and cache them."""
        for item in results:
            sd = item.get("series_description") or {}
            db_id = sd.get("database_id")
            db_name = sd.get("database_name")
            if db_id and db_name:
                self._db_name_cache[db_id] = db_name

    async def resolve_db_name(self, database_id: str) -> str | None:
        """Resolve a database_id to its human-readable name via lightweight search."""
        if database_id in self._db_name_cache:
            return self._db_name_cache[database_id]
        # Validate database_id to prevent OData filter injection
        if not re.fullmatch(r"[A-Za-z0-9_]+", database_id):
            return None
        body = {"search": "*", "filter": f"series_description/database_id eq '{database_id}'", "top": 1}
        result = await self._request("POST", "/data360/searchv2", json_body=body)
        if isinstance(result, dict) and result.get("success") is False:
            return None
        items = result.get("value", [])
        if items:
            self.cache_db_names(items)
            return self._db_name_cache.get(database_id)
        return None

    async def enrich_citation_source(self, records: list[dict]) -> None:
        """Add CITATION_SOURCE to each record. Never modifies DATA_SOURCE."""
        db_ids_to_resolve: set[str] = set()
        for record in records:
            if not record.get("DATA_SOURCE") and record.get("DATABASE_ID"):
                db_ids_to_resolve.add(record["DATABASE_ID"])

        for db_id in db_ids_to_resolve:
            if db_id not in self._db_name_cache:
                await self.resolve_db_name(db_id)

        for record in records:
            data_source = record.get("DATA_SOURCE")
            if data_source:
                record["CITATION_SOURCE"] = data_source
            else:
                db_id = record.get("DATABASE_ID", "")
                record["CITATION_SOURCE"] = self._db_name_cache.get(db_id, db_id)

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> "Data360Client":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
