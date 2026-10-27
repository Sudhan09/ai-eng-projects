import pytest

httpx = pytest.importorskip("httpx")
from demo import web  # noqa: E402


def flaky_api(request):
    return httpx.Response(200, json={"ok": True})


async def test_mock_transport():
    async with web.make_client(httpx.MockTransport(flaky_api)) as client:
        assert await web.fetch_json(client, "/x") == {"ok": True}
