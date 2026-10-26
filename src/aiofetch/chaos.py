import asyncio
import random
import zlib
from collections.abc import Iterable, Mapping

import httpx

Answer = int | str  # a status code like 503, or a word like "timeout"


def payload(path: str) -> dict[str, object]:
    kind = path.split("/")[1]
    name = path.split("/")[-1]
    if kind == "embed":
        rng = random.Random(zlib.crc32(name.encode()))
        vector: list[float] = []
        for _ in range(8):
            vector.append(round(rng.gauss(0, 1), 4))
        return {"text": name, "vector": vector}
    return {"id": name, "name": f"item {name}"}


class ChaosAPI:
    def __init__(
        self,
        *,
        script: Mapping[str, Iterable[Answer]] | None = None,
        fail_rate: float = 0.0,
        limit_rate: float = 0.0,
        latency: float = 0.0,
        retry_after: str = "1",
        seed: int = 0,
        down: bool = False,
    ) -> None:
        self.script = {path: list(answers) for path, answers in (script or {}).items()}
        self.fail_rate = fail_rate
        self.limit_rate = limit_rate
        self.latency = latency
        self.retry_after = retry_after
        self.down = down
        self.rng = random.Random(seed)
        self.calls: dict[str, int] = {}
        self.total = 0
        self.in_flight = 0
        self.peak = 0

    def next_answer(self, path: str) -> Answer:
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

    async def __call__(self, request: httpx.Request) -> httpx.Response:
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
            if isinstance(answer, str):
                raise ValueError(f"chaos: unknown scripted answer {answer!r}")
            return httpx.Response(answer, json={"error": "busy"})
        finally:
            self.in_flight -= 1
