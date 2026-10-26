import asyncio
import json
import random
import zlib
from collections.abc import Iterable, Mapping

import httpx

from .errors import TransientError
from .transport import Response

Answer = int | str  # a status code like 503, or a word like "timeout"


def tagged(item_id: int) -> dict[str, object]:
    if item_id >= 3000:
        return {"status": "moved", "id": item_id, "movedTo": item_id - 3000}
    if item_id < 1000:
        item = {"id": item_id, "name": f"item {item_id}", "priceCents": 250 + item_id}
        return {"status": "ok", "item": item}
    if item_id < 2000:
        return {"status": "not_found", "id": item_id}
    return {"status": "error", "code": "bad_id", "message": f"no id {item_id}"}


def broken(answer: dict[str, object], rng: random.Random) -> dict[str, object]:
    damage = rng.choice(["no tag", "unknown tag", "extra field", "renamed field"])
    if damage == "no tag":
        del answer["status"]
    elif damage == "unknown tag":
        answer["status"] = "pending"
    elif damage == "extra field":
        answer["debug"] = True
    elif answer["status"] == "ok":
        item = answer["item"]
        if isinstance(item, dict):
            item["price"] = item.pop("priceCents")
    elif answer["status"] == "not_found":
        answer["itemId"] = answer.pop("id")
    else:
        answer["msg"] = answer.pop("message")
    return answer


def seeded_answers(
    size: int = 10_000, bad_share: float = 0.2, seed: int = 4
) -> list[tuple[dict[str, object], str | None]]:
    rng = random.Random(seed)
    pairs: list[tuple[dict[str, object], str | None]] = []
    for n in range(size):
        answer = tagged(n % 3000)
        if rng.random() < bad_share:
            pairs.append((broken(answer, rng), None))
        else:
            status = answer["status"]
            pairs.append((answer, str(status)))
    return pairs


def payload(path: str) -> dict[str, object]:
    kind = path.split("/")[1]
    name = path.split("/")[-1]
    if kind == "v2":
        return tagged(int(name))
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
