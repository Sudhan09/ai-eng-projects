import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Protocol, runtime_checkable

import httpx

from .errors import FetchError, PermanentError, TransientError


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> object:
        data: object = json.loads(self.body)
        return data


@runtime_checkable
class HttpTransport(Protocol):
    async def get(self, path: str, params: Mapping[str, str] | None = None) -> Response: ...

    async def aclose(self) -> None: ...


def make_client(
    base_url: str,
    *,
    max_connections: int = 20,
    timeout: float = 10.0,
    transport: httpx.AsyncBaseTransport | None = None,
    headers: Mapping[str, str] | None = None,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url,
        headers=headers,
        limits=httpx.Limits(max_connections=max_connections),
        timeout=httpx.Timeout(timeout, connect=5.0),
        transport=transport,
    )


def is_transient_status(status: int, body: str = "") -> bool:
    if "insufficient_quota" in body:
        return False
    return status in (408, 409, 429) or status >= 500


def retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    if value.strip().isdigit():
        return float(value)
    return None


def error_for(url: str, response: Response) -> FetchError:
    reason = f"{response.status} {HTTPStatus(response.status).phrase}"
    if is_transient_status(response.status, response.body.decode()):
        hint = retry_after(response.headers.get("retry-after"))
        return TransientError(url, reason, retry_after=hint)
    return PermanentError(url, reason)


class HttpxTransport:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def get(self, path: str, params: Mapping[str, str] | None = None) -> Response:
        try:
            response = await self.client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise TransientError(path, f"timeout ({type(exc).__name__})") from exc
        except httpx.TransportError as exc:
            raise TransientError(path, type(exc).__name__) from exc
        return Response(response.status_code, response.content, dict(response.headers))

    async def aclose(self) -> None:
        await self.client.aclose()


async def get_json(
    transport: HttpTransport, path: str, params: Mapping[str, str] | None = None
) -> object:
    response = await transport.get(path, params)
    if response.status >= 400:
        raise error_for(path, response)
    return response.json()
