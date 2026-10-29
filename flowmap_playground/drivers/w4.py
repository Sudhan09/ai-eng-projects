"""Week 4 (aiofetch): each Part's entry, and suggested inputs that together reach every component of that Part.

The "W3" pill and Part 1 still have ChaosAPI, so they use Week 3's Part 5 table. From Part 2 your client builds its
own HttpxTransport and only the network under httpx is faked (FlakyAPI answers), so the seam runs as it really would.
Input: paths or ids, "=" scripts the fake's answers (/items/1=503,503,200), rpm=120 turns on the rate limiter, "torn"
(jsonl) adds half a line to the file. Your project's code is imported inside each entry, so this file loads at any Part.
"""

import asyncio
import os
from pathlib import Path

import w3
from _input import few, last, options, scripted, with_call, words


def fake_network(script):
    """An httpx client made without a transport talks to FlakyAPI instead of the network."""
    import httpx
    from aiofetch.flaky import FlakyAPI
    api = FlakyAPI(script=script)
    real = httpx.AsyncClient.__init__

    def init(self, *args, transport=None, **kwargs):
        real(self, *args, transport=transport or httpx.MockTransport(api), **kwargs)

    httpx.AsyncClient.__init__ = init


def client(o):
    from aiofetch.client import AiofetchClient
    return AiofetchClient("http://api.test", **({"requests_per_minute": int(o["rpm"])} if "rpm" in o else {}))


def run_fetch_many(text):  # from Part 2
    rest, o = options(text, "rpm")
    paths, script = scripted(rest)
    fake_network(script)

    async def go():
        async with client(o) as c:
            return await c.fetch_many(paths)

    return asyncio.run(go())


def run_get_item(text):  # from Part 3
    rest, o = options(text, "rpm")
    ids, script = scripted(rest, lambda i: f"/v2/items/{i}")
    if not ids or not all(i.isdigit() for i in ids):
        raise ValueError("get_item takes item ids, e.g. 7 1500 3007")  # before any of your code runs
    fake_network(script)

    async def go():
        async with client(o) as c:
            return [await c.get_item(int(i)) for i in ids]

    return asyncio.run(go())


def run_jsonl(text):  # from Part 4
    from aiofetch.storage import ReadStats, read_jsonl, write_jsonl
    words = text.split()
    rest, o = options(" ".join(w for w in words if w != "torn"), "rpm")
    paths, script = scripted(rest)
    if not paths:
        raise ValueError("jsonl takes paths, e.g. /items/1 /items/2 torn")
    fake_network(script)

    async def go():
        async with client(o) as c:
            return await c.fetch_many(paths)

    rows = [result.to_row() for result in asyncio.run(go())]
    path = Path("rows.jsonl")  # in the empty folder the recorder runs in
    write_jsonl(path, rows)
    if "torn" in words:
        with path.open("a") as sink:
            sink.write('{"url": "/items/9", "sec\n')  # half a line, as if writing stopped midway (your Part 4 test's)
    stats = ReadStats()
    return {"rows": list(read_jsonl(path, stats)), "stats": stats}


def run_main(text):  # Part 5: python -m aiofetch, with your settings coming from the environment
    from aiofetch.__main__ import main
    from aiofetch.settings import get_settings
    rest, o = options(text, "rpm")
    paths, script = scripted(rest)
    for name in [n for n in os.environ if n.startswith("AIOFETCH_")]:
        del os.environ[name]  # only these settings, never your shell's
    os.environ.update(AIOFETCH_BASE_URL="http://api.test", AIOFETCH_API_KEY="playground-not-a-real-key")
    if "rpm" in o:
        os.environ["AIOFETCH_REQUESTS_PER_MINUTE"] = o["rpm"]
    get_settings.cache_clear()
    fake_network(script)
    return asyncio.run(main(paths))


# your tests' values -> the words you'd type (suggest.py): the paths or ids, the fake's script, the rate limit
FAKE = "flaky.FlakyAPI.__init__"


def rpm(before):
    n = last(before, "client.AiofetchClient.__init__", "requests_per_minute")
    return f" rpm={n}" if isinstance(n, int) and n else ""


def paths_typed(a, before):
    paths = few(a.get("paths"))
    return words(paths, last(before, FAKE, "script")) + rpm(before) if paths else None


def item_typed(a, before):
    i = a.get("item_id")
    return words([i], last(before, FAKE, "script"), lambda i: f"/v2/items/{i}") + rpm(before) if type(i) is int else None


def rows_typed(a, before):
    rows = a.get("records")
    urls = few([r.get("url") for r in rows if isinstance(r, dict)]) if isinstance(rows, list) and rows else None
    return " ".join(urls) if urls and len(urls) == len(rows) else None


FETCH_MANY = {"label": "client.fetch_many", "hint": "/items/1 /items/2=404   rpm=120", "run": run_fetch_many,
              "from": {"client.AiofetchClient.fetch_many": paths_typed}}
GET_ITEM = {"label": "client.get_item", "hint": "7   1500   3007", "run": run_get_item, "from": {"client.AiofetchClient.get_item": item_typed}}
JSONL = {"label": "fetch → write → read jsonl", "hint": "/items/1 /items/2 torn", "run": run_jsonl, "from": {"storage.write_jsonl": rows_typed}}
MAIN = {"label": "python -m aiofetch", "hint": "/v2/items/7   /items/1=503,503,200", "run": run_main,
        "from": {"__main__.main": lambda a, before: words(few(a.get("paths")) or [], last(before, FAKE, "script")) or None}}

GOOD = ("fetch_many", "/items/1 /items/2", "good", "Two items at once, through your real transport")
BAD = ("fetch_many", "/items/1 /items/2=404", "bad", "One 404: a failed result, the other fine")
RETRY = ("fetch_many", "/items/1=503,503,200 /items/2 rpm=120", "more", "503, 503, then 200: the retry, paced by the rate limiter")

PARTS = {
    "W3": w3.PARTS["5"],
    "1": w3.PARTS["5"],
    "2": {"entries": {"fetch_many": FETCH_MANY}, "scenarios": [GOOD, BAD, RETRY]},
    "3": {"entries": {"get_item": GET_ITEM, "fetch_many": FETCH_MANY}, "scenarios": [
        ("get_item", "7", "good", "Item 7 comes back as a typed ItemFound"),
        ("get_item", "1500", "bad", "Item 1500 doesn't exist: a typed ItemMissing"),
        ("get_item", "3007 rpm=120", "more", "Item 3007 has moved: the detour to item 7, paced by the rate limiter"),
        RETRY,
    ]},
    "4": {"entries": {"jsonl": JSONL, "get_item": GET_ITEM, "fetch_many": FETCH_MANY}, "scenarios": [
        ("jsonl", "/items/1 /items/2", "good", "Fetch two items, write them to a file, read them back"),
        ("jsonl", "/items/1 /items/2 torn", "bad", "A half-written line: skipped and counted in ReadStats"),
        ("get_item", "1500 3007 rpm=120", "more", "A missing item and a moved one, paced by the rate limiter"),
        RETRY,
    ]},
    "5": {"entries": {"main": MAIN, "jsonl": JSONL, "get_item": GET_ITEM, "fetch_many": FETCH_MANY}, "scenarios": [
        ("main", "/v2/items/7", "good", "python -m aiofetch: your settings, one item, exit 0"),
        ("main", "/items/1 /items/2=404", "bad", "One path fails: the command exits 1"),
        ("jsonl", "/items/1 /items/2 torn", "more", "Rows to a file and back, past a half-written line"),
        ("get_item", "1500 3007 rpm=120", "more", "A missing item and a moved one, paced by the rate limiter"),
    ]},
}
with_call(PARTS, 'storage.is_json_object({"url": "/items/1"})')
