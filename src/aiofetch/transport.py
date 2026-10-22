import asyncio

import httpx  
from aiofetch.errors import error_for, TransientError

def make_client(base_url, *, max_connections=20, timeout=10.0, transport=None):
    return httpx.AsyncClient(
        base_url=base_url,
        limits=httpx.Limits(max_connections=max_connections,
                            max_keepalive_connections=max_connections),
        timeout=httpx.Timeout(timeout, connect=5.0),
        transport=transport,
    )

async def get_json(client, path, params=None):
    try:
        response = await client.get(path, params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        raise error_for(path, exc.response) from exc
    except httpx.TimeoutException as exc:
        raise TransientError(path, f"timeout ({type(exc).__name__})") from exc
    except httpx.TransportError as exc:
        raise TransientError(path, type(exc).__name__) from exc
