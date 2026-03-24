"""Async HTTP client for the World Bank Data360 API."""

import asyncio
import logging

import httpx

from mcp_server.config import (
    BASE_URL,
    MAX_RETRIES,
    REQUEST_TIMEOUT,
    RETRY_BACKOFF_BASE,
)

logger = logging.getLogger(__name__)


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

    async def _get_client(self) -> httpx.AsyncClient:
        async with self._lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> "Data360Client":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
