import asyncio
import json
import random

from aiofetch.transport import Response

WORDS = (
    "the", "model", "streams", "each", "token", "as", "soon", "as", "it", "is", "ready",
    "so", "you", "see", "words", "arrive", "one", "by", "one", "instead", "of", "waiting",
) 

def token_at(prompt, index):
    return " " + random.Random(f"{prompt}|{index}").choice(WORDS)

class FakeProvider:
    def __init__(self, delay=0.0, fail_from=None, status=503):
        self.delay = delay
        self.fail_from = fail_from
        self.status = status
        self.calls = 0
        self.closed = False

    async def get(self, path, params=None):
        self.calls += 1
        if self.fail_from is not None and self.calls >= self.fail_from:
            if self.status == "hang":
                await asyncio.sleep(3600)
            return Response(self.status, b'{"error": "failed on purpose"}')
        await asyncio.sleep(self.delay)
        prompt = params["prompt"]
        start = int(params["start"])
        count = int(params["count"])
        tokens = []
        for i in range(start, start + count):
            tokens.append(token_at(prompt, i))
        body = json.dumps({"tokens": tokens, "done": False}).encode()
        return Response(200, body)

    async def aclose(self):
        self.closed = True

class FakeStreamingLLM:
    def __init__(self, delay=0.005, jitter=0.002, seed=0):
        self.delay = delay
        self.jitter = jitter
        self.seed = seed

    async def stream(self, prompt, max_tokens):
        rng = random.Random(self.seed)
        for i in range(max_tokens):
            await asyncio.sleep(self.delay + rng.uniform(0, self.jitter))
            yield token_at(prompt, i)