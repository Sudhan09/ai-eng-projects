import asyncio
import random

import httpx


def payload(path):
    item_id = path.split("/")[-1]  # "/items/7" -> "7"
    return {"id": item_id, "name": f"item {item_id}"}


class ChaosAPI:
    def __init__(
        self,
        *,
        script=None,
        fail_rate=0.0,
        limit_rate=0.0,
        latency=0.0,
        retry_after="1",
        seed=0,
        down=False,
    ):
        self.script = {path: list(answers) for path, answers in (script or {}).items()}
        self.fail_rate = fail_rate
        self.limit_rate = limit_rate
        self.latency = latency
        self.retry_after = retry_after
        self.down = down
        self.rng = random.Random(seed)
        self.calls = {}
        self.total = 0
        self.in_flight = 0
        self.peak = 0

    def next_answer(self, path):
        if self.script.get(path):
            return self.script[path].pop(0)
        if self.down:
            return 503
        roll = self.rng.random()
        if roll < self.fail_rate:
            return 503
        if roll < self.fail_rate + self.limit_rate:
            return 429
        return 200

    async def __call__(self, request):
        path = request.url.path
        self.calls[path] = self.calls.get(path, 0) + 1
        self.total += 1
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        try:
            await asyncio.sleep(self.latency)
            answer = self.next_answer(path)

            if answer == "timeout":
                raise httpx.ReadTimeout("chaos: no answer", request=request)
            if answer == "reset":
                raise httpx.ReadError("chaos: connection reset", request=request)
            if answer == "refused":
                raise httpx.ConnectError("chaos: connection refused", request=request)
            if answer == "hang":
                await asyncio.sleep(3600)
            if answer == "quota":
                return httpx.Response(429, json={"error": {"code": "insufficient_quota"}})
            if answer == 429:
                headers = {"Retry-After": self.retry_after}
                return httpx.Response(429, headers=headers, json={"error": "slow down"})
            if answer == 200:
                return httpx.Response(200, json=payload(path))
            return httpx.Response(answer, json={"error": "busy"})
        finally:
            self.in_flight -= 1
