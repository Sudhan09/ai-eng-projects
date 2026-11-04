from typing import Protocol

from aiofetch.errors import FetchError
from pydantic import ValidationError

from stream_svc.errors import UpstreamFailed, from_fetch_error
from stream_svc.models import TokenPage


class TokenSource(Protocol):
    def stream(self, prompt, max_tokens): ...


class UpstreamSource:
    def __init__(self, client, page_size=8, retry_after=5):
        self.client = client
        self.page_size = page_size
        self.retry_after = retry_after

    async def stream(self, prompt, max_tokens):
        start = 0
        while start < max_tokens:
            count = min(self.page_size, max_tokens - start)
            params = {"prompt": prompt, "start": str(start), "count": str(count)}
            try:
                data = await self.client.get_json("/v1/tokens", params)
            except FetchError as exc:
                raise from_fetch_error(exc, self.retry_after) from exc
            try:
                page = TokenPage.model_validate(data)
            except ValidationError as exc:
                raise UpstreamFailed() from exc
            for token in page.tokens:
                yield token
            start += len(page.tokens)
            if page.done or not page.tokens:
                return
