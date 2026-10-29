"""Week 3 (aiofetch): each Part's entry, and suggested inputs that together reach every component of that Part.

Input: paths (/items/7), "=" scripts the fake's answers for a path (/items/7=503,503,200; words like hang, timeout),
and settings rpm=120 (the rate limiter, from Part 4) and timeout=0.2 (seconds per try, from Part 3).
Everything runs on ChaosAPI, the fake server, through httpx's MockTransport. Your code is imported inside each entry.
"""

import asyncio

from _input import few, last, options, scripted, with_call, words


def chaos(script):
    import httpx
    from aiofetch.chaos import ChaosAPI
    return httpx.MockTransport(ChaosAPI(script=script))


def run_get_json(text):  # Part 1
    from aiofetch.transport import get_json, make_client
    paths, script = scripted(text)

    async def go():
        async with make_client("http://api.test", transport=chaos(script)) as client:
            return [await get_json(client, p) for p in paths]

    return asyncio.run(go())


def run_retry_call(text):  # Part 2
    from aiofetch.retry import retry_call
    from aiofetch.transport import get_json, make_client
    paths, script = scripted(text)

    async def go():
        async with make_client("http://api.test", transport=chaos(script)) as client:
            return [await retry_call(lambda: get_json(client, p)) for p in paths]

    return asyncio.run(go())


def client_options(o):
    return {**({"timeout": float(o["timeout"])} if "timeout" in o else {}),
            **({"requests_per_minute": int(o["rpm"])} if "rpm" in o else {})}


def run_fetch_many(text):  # from Part 3
    from aiofetch.client import AiofetchClient
    rest, o = options(text, "rpm", "timeout")
    paths, script = scripted(rest)

    async def go():
        async with AiofetchClient("http://api.test", transport=chaos(script), **client_options(o)) as client:
            return await client.fetch_many(paths)

    return asyncio.run(go())


def run_embed(text):  # Part 5: your words become vectors, then one similarity matrix
    from aiofetch.client import AiofetchClient
    from aiofetch.embed import cosine_matrix, to_matrix

    async def go():
        async with AiofetchClient("http://api.test", transport=chaos({})) as client:
            return await client.fetch_many([f"/embed/{w}" for w in text.split()])

    matrix = to_matrix([r.value["vector"] for r in asyncio.run(go())])
    return {"vectors": matrix, "similarity": cosine_matrix(matrix)}


# your tests' values -> the words you'd type (suggest.py): the paths, ChaosAPI's script, the client's settings
CHAOS = "chaos.ChaosAPI.__init__"


def path_typed(a, before):
    return words([a["path"]], last(before, CHAOS, "script")) if isinstance(a.get("path"), str) and " " not in a["path"] else None


def retried_typed(a, before):  # get_json inside retry_call: the test's retry
    return path_typed(a, before) if last(before, "retry.retry_call") is not None else None


def settings_typed(before):
    o = last(before, "client.AiofetchClient.__init__") or {}
    rpm, timeout = o.get("requests_per_minute"), o.get("timeout")
    return (f" rpm={rpm}" if isinstance(rpm, int) and rpm else "") + (f" timeout={timeout}" if isinstance(timeout, (int, float)) and timeout < 1 else "")


def paths_typed(a, before):
    paths = few(a.get("paths"))
    if not paths or any(p.startswith("/embed/") for p in paths):
        return None
    return words(paths, last(before, CHAOS, "script")) + settings_typed(before)


def embed_typed(a, before):
    paths = few(a.get("paths"))
    return " ".join(p[len("/embed/"):] for p in paths) if paths and all(p.startswith("/embed/") for p in paths) else None


GET_JSON = {"label": "transport.get_json", "hint": "/items/7   /items/7=503", "run": run_get_json, "from": {"transport.get_json": path_typed}}
RETRY = {"label": "retry_call(get_json)", "hint": "/items/7=503,503,200", "run": run_retry_call, "from": {"transport.get_json": retried_typed}}
FETCH_MANY = {"label": "client.fetch_many", "hint": "/items/1 /items/3=404   rpm=120   timeout=0.2", "run": run_fetch_many,
              "from": {"client.AiofetchClient.fetch_many": paths_typed}}
EMBED = {"label": "embeddings", "hint": "cat dog car", "run": run_embed, "from": {"client.AiofetchClient.fetch_many": embed_typed}}

GOOD = ("fetch_many", "/items/1 /items/2 /items/3", "good", "Three items at once")
BAD = ("fetch_many", "/items/1 /items/3=404", "bad", "One 404 among them: a failed result, the others fine")
HUNG = ("fetch_many", "/items/1=hang,200 timeout=0.2", "more", "A hung try times out, the retry gets it")

PARTS = {
    "1": {"entries": {"get_json": GET_JSON}, "scenarios": [
        ("get_json", "/items/7", "good", "One request: the item's JSON comes back"),
        ("get_json", "/items/7=503", "bad", "A 503 becomes a TransientError"),
        ("get_json", "/items/7=404", "more", "A 404 becomes a PermanentError"),
    ]},
    "2": {"entries": {"retry_call": RETRY, "get_json": GET_JSON}, "scenarios": [
        ("retry_call", "/items/7", "good", "One try, the item comes back"),
        ("retry_call", "/items/7=404", "bad", "A 404 is final: no retry"),
        ("retry_call", "/items/7=503,503,200", "more", "503, 503, then 200: watch the retry"),
    ]},
    "3": {"entries": {"fetch_many": FETCH_MANY}, "scenarios": [GOOD, BAD, HUNG]},
    "4": {"entries": {"fetch_many": FETCH_MANY}, "scenarios": [
        GOOD, BAD, HUNG, ("fetch_many", "/items/1 /items/2 rpm=120", "more", "Two requests paced by the rate limiter")]},
    "5": {"entries": {"fetch_many": FETCH_MANY, "embeddings": EMBED}, "scenarios": [
        GOOD, BAD, ("fetch_many", "/items/1=hang,200 /items/2 rpm=120 timeout=0.2", "more", "A timeout and the rate limiter in one batch"),
        ("embeddings", "cat dog car", "more", "Three words become vectors and a similarity matrix")]},
}
with_call(PARTS, 'transport.is_transient_status(503)')
