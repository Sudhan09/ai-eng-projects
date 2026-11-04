import hashlib
import secrets

from fastapi import Cookie, Depends, Header

from stream_svc.errors import AuthError
from stream_svc.settings import get_settings


def key_hash(key):
    return hashlib.sha256(key.encode()).hexdigest()


async def verify_api_key(
    settings=Depends(get_settings),
    x_api_key=Header(None),
    stream_key=Cookie(None),
):
    key = x_api_key or stream_key
    if not key:
        raise AuthError()
    if not secrets.compare_digest(key_hash(key), settings.api_key_sha256):
        raise AuthError()
