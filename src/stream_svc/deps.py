from fastapi import Depends, Request

from stream_svc.security import verify_api_key
from stream_svc.sources import UpstreamSource


async def get_upstream(request: Request):
    return request.app.state.upstream


async def get_token_source(upstream=Depends(get_upstream)):
    return UpstreamSource(upstream)


def get_authed_source(a=Depends(verify_api_key), source=Depends(get_token_source)):
    return source
