from fastapi import Depends, Header, HTTPException

from stream_svc.settings import get_settings


async def verify_api_key(setting=Depends(get_settings), x_api_key=Header(None)):
    if not x_api_key:
        raise HTTPException(401, "A valid API key is required.")
