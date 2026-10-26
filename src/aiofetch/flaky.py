import asyncio
import json
import random
import zlib
from collections.abc import Iterable, Mapping

import httpx

from .errors import TransientError
from .transport import Response

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


def json_response(status: int, data: object, headers: Mapping[str, str] | None = None) -> Response:
    all_headers = {"content-type": "application/json"}
    if headers is not None:
        all_headers.update(headers)
    return Response(status, json.dumps(data).encode(), all_headers)


class FlakyAPI:
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

    async def get(self, path: str, params: Mapping[str, str] | None = None) -> Response:
        self.calls[path] = self.calls.get(path, 0) + 1
        self.total += 1
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        try:
            await asyncio.sleep(self.latency)
            answer = self.next_answer(path)

            if answer == "timeout":
                raise TransientError(path, "timeout (ReadTimeout)")
            if answer == "reset":
                raise TransientError(path, "ReadError")
            if answer == "refused":
                raise TransientError(path, "ConnectError")
            if answer == "hang":
                await asyncio.sleep(3600)
            if answer == "quota":
                return json_response(429, {"error": {"code": "insufficient_quota"}})
            if answer == 429:
                headers = {"retry-after": self.retry_after}
                return json_response(429, {"error": "slow down"}, headers)
            if answer == 404:
                return json_response(404, {"error": "no such item"})
            if answer == 200:
                return json_response(200, payload(path))
            if isinstance(answer, str):
                raise ValueError(f"flaky: unknown scripted answer {answer!r}")
            return json_response(answer, {"error": "busy"})
        finally:
            self.in_flight -= 1

    async def aclose(self) -> None:
        pass

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        try:
            response = await self.get(request.url.path)
        except TransientError as exc:
            message = f"flaky: {exc.reason}"
            if exc.reason == "timeout (ReadTimeout)":
                raise httpx.ReadTimeout(message, request=request) from exc
            if exc.reason == "ReadError":
                raise httpx.ReadError(message, request=request) from exc
            raise httpx.ConnectError(message, request=request) from exc
        return httpx.Response(response.status, content=response.body, headers=response.headers)
