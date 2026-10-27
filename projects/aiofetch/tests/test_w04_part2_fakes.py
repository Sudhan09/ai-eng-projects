import asyncio
import subprocess
import sys

import httpx

from aiofetch.fake import FakeTransport
from aiofetch.flaky import FlakyAPI
from aiofetch.transport import HttpTransport, HttpxTransport

FITS = """\
import httpx

from aiofetch.fake import FakeTransport
from aiofetch.flaky import FlakyAPI
from aiofetch.transport import HttpTransport, HttpxTransport, Response

fits: list[HttpTransport] = [
    HttpxTransport(httpx.AsyncClient()),
    FakeTransport({}),
    FlakyAPI(),
]


class WrongFake:
    async def get(self, path: int) -> Response:
        return Response(200)

    async def aclose(self) -> None:
        pass


wrong: HttpTransport = WrongFake()
"""


def checkers(tmp_path, source):
    """Run mypy --strict and pyright on `source`; return what each printed."""
    path = tmp_path / "seeded.py"
    path.write_text(source)
    outputs = []
    # pyright reads the packages of the Python it's given: the one running the test
    for tool in (["mypy", "--strict"], ["pyright", "--pythonpath", sys.executable]):
        run = subprocess.run(
            [sys.executable, "-m", *tool, str(path)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        outputs.append(run.stdout)
    return outputs


def test_flaky_api_answers_as_a_transport():
    response = asyncio.run(FlakyAPI().get("/items/7"))
    assert (response.status, response.json()) == (200, {"id": "7", "name": "item 7"})


def test_the_fake_answers_its_paths_and_records_every_request():
    fake = FakeTransport({"/items/7": {"id": "7"}})

    async def main():
        found = await fake.get("/items/7", {"fields": "id"})
        missing = await fake.get("/items/8")
        await fake.aclose()
        return found, missing

    found, missing = asyncio.run(main())
    assert (found.status, found.json(), missing.status) == (200, {"id": "7"}, 404)
    assert fake.requests == [("/items/7", {"fields": "id"}), ("/items/8", {})]
    assert fake.closed


def test_the_real_transport_and_both_fakes_are_http_transports():
    assert isinstance(HttpxTransport(httpx.AsyncClient()), HttpTransport)
    assert isinstance(FlakyAPI(), HttpTransport)
    assert isinstance(FakeTransport({}), HttpTransport)


def test_the_real_transport_and_both_fakes_fit_the_seam_as_types(tmp_path):
    mypy, pyright = checkers(tmp_path, FITS)
    assert mypy.count(": error:") == 1 and '"WrongFake"' in mypy, mypy
    assert "1 error, 0 warnings" in pyright and '"WrongFake"' in pyright, pyright
