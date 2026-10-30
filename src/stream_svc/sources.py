from typing import Protocol

from stream_svc.models import TokenPage


class TokenSource(Protocol):
    def stream(self, prompt, max_tokens): ...


class UpstreamSource:
    def __init__(self, client, page_size=8):
        self.client = client
        self.page_size = page_size

    async def stream(self, prompt, max_tokens):
        start = 0
        while start < max_tokens:
            count = min(self.page_size, max_tokens - start)
            params = {"prompt": prompt, "start": str(start), "count": str(count)}
            data = await self.client.get_json("/v1/tokens", params)
            page = TokenPage.model_validate(data)
            for token in page.tokens:
                yield token
            start += len(page.tokens)
            if page.done or not page.tokens:
                return
