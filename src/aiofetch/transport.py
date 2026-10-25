import httpx

from .errors import PermanentError, TransientError


def make_client(base_url, *, max_connections=20, timeout=10.0, transport=None):
    return httpx.AsyncClient(
        base_url=base_url,
        limits=httpx.Limits(max_connections=max_connections),
        timeout=httpx.Timeout(timeout, connect=5.0),
        transport=transport,
    )


def is_transient_status(status, body=""):
    if "insufficient_quota" in body:
        return False
    return status in (408, 409, 429) or status >= 500


def error_for(url, response):
    reason = f"{response.status_code} {response.reason_phrase}"
    if is_transient_status(response.status_code, response.text):
        return TransientError(url, reason)
    return PermanentError(url, reason)


async def get_json(client, path, params=None):
    try:
        response = await client.get(path, params=params)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise error_for(path, exc.response) from exc
    except httpx.TimeoutException as exc:
        raise TransientError(path, f"timeout ({type(exc).__name__})") from exc
    except httpx.TransportError as exc:
        raise TransientError(path, type(exc).__name__) from exc
    return response.json()
