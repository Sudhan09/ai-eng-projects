from aiofetch import AiofetchClient
from fastapi import Depends

from stream_svc.fakes import FakeProvider
from stream_svc.security import verify_api_key
from stream_svc.settings import get_settings
from stream_svc.sources import UpstreamSource


async def get_token_source(settings=Depends(get_settings)):
    transport = None
    if settings.fake_upstream:
        transport = FakeProvider(delay=0.02)
    client = AiofetchClient(
        settings.upstream_url,
        attempts=settings.upstream_attempts,
        timeout=settings.upstream_timeout,
        transport=transport,
    )
    async with client:
        yield UpstreamSource(client)

def get_authed_source(a=Depends(verify_api_key), source=Depends(get_token_source)):
    return source