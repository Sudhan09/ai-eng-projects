import asyncio
import random

import httpx


class ChaosAPI:
    def __init__(self, script=None, latency=0, fail_rate=0, 
                 limit_rate=0, retry_after=1, seed=0, down=False):
        self.script = {path: list(answers) for path, answers in (script or {}).items()}
        self.latency = latency
        self.fail_rate =  fail_rate
        self.limit_rate = limit_rate
        self.retry_after = retry_after
        self.down = down
        self.rng = random.Random(seed)
        self.calls = {}
        self.total = 0
        self.in_flight = 0
        self.peak = 0

    def next_answer(self, path):
        if self.down:
            return 503
        answers = self.script.get(path)
        if answers:
            return answers.pop(0)
        roll = self.rng.random()
        if roll < self.fail_rate:
            return 503
        elif roll < self.fail_rate + self.limit_rate:
            return 429
        else:
            return 200


    async def __call__(self, request):
        path = request.url.path                               # "/items/7"
        self.calls[path] = self.calls.get(path, 0) + 1        # count this path
        self.total += 1                                       # count all requests
        self.in_flight += 1                                   # one more being served
        self.peak = max(self.peak, self.in_flight)            # busiest moment so far
        try:
            await asyncio.sleep(self.latency)                 # be slow if asked
            answer = self.next_answer(path)                   # e.g. 503, 200, "hang"
            if answer == "timeout":
                raise httpx.ReadTimeout("timeout", request=request)   # pretend: too slow
            if answer == "refused":
                raise httpx.ConnectError("refused", request=request)  # pretend: can't connect
            if answer == "hang":
                await asyncio.sleep(3600)                     # never reply (1 hour)
            if answer == "quota":
                return httpx.Response(429, json={"error": "insufficient_quota"})
            if answer == 429:
                return httpx.Response(429, headers={"Retry-After": str(self.retry_after)})
            if answer == 200:
                item_id = path.split("/")[-1]                 # "/items/7" → "7"
                return httpx.Response(200, json={"id": item_id, "name": f"item {item_id}"})
            return httpx.Response(answer)                     # anything else, e.g. 503, 404
        finally:
            self.in_flight -= 1                               # done serving, always runs