from __future__ import annotations

import asyncio
import threading
from typing import Any

import httpx

_creds_lock = threading.Lock()
_cached_creds: Any = None
_shared_client: httpx.AsyncClient | None = None


def _refresh_gcp_token_sync() -> str:
    global _cached_creds
    import google.auth
    import google.auth.transport.requests

    with _creds_lock:
        if _cached_creds is None:
            _cached_creds, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        if not _cached_creds.valid or _cached_creds.expired:
            _cached_creds.refresh(google.auth.transport.requests.Request())
        return str(_cached_creds.token)


async def get_gcp_access_token() -> str:
    """Returns a cached GCP ADC OAuth2 token, refreshing off the event loop only when expired."""
    return await asyncio.to_thread(_refresh_gcp_token_sync)


def get_shared_http_client(timeout: float = 60.0) -> httpx.AsyncClient:
    """Returns a connection-pooled shared httpx.AsyncClient."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
    return _shared_client
