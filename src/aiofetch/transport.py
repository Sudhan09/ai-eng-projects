from collections.abc import Mapping

import httpx

from .errors import FetchError, PermanentError, TransientError


def make_client(
    base_url: str,
    *,
    max_connections: int = 20,
    timeout: float = 10.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url,
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


def error_for(url: str, response: httpx.Response) -> FetchError:
    reason = f"{response.status_code} {response.reason_phrase}"
    if is_transient_status(response.status_code, response.text):
        hint = retry_after(response.headers.get("Retry-After"))
        return TransientError(url, reason, retry_after=hint)
    return PermanentError(url, reason)


async def get_json(
    client: httpx.AsyncClient, path: str, params: Mapping[str, str] | None = None
) -> object:
    try:
        response = await client.get(path, params=params)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise error_for(path, exc.response) from exc
    except httpx.TimeoutException as exc:
        raise TransientError(path, f"timeout ({type(exc).__name__})") from exc
    except httpx.TransportError as exc:
        raise TransientError(path, type(exc).__name__) from exc
    data: object = response.json()  # httpx says Any; we promise only object
    return data
