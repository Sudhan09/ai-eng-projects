import json
from collections.abc import Mapping

from .transport import Response


class FakeTransport:
    def __init__(self, answers: Mapping[str, object]) -> None:
        self.answers = answers
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.closed = False

    async def get(self, path: str, params: Mapping[str, str] | None = None) -> Response:
        if params is None:
            params = {}
        self.requests.append((path, dict(params)))
        headers = {"content-type": "application/json"}
        if path in self.answers:
            return Response(200, json.dumps(self.answers[path]).encode(), headers)
        return Response(404, b'{"error": "no such item"}', headers)

    async def aclose(self) -> None:
        self.closed = True
