import httpx


def make_client(transport):
    return httpx.AsyncClient(transport=transport, base_url="http://api.test")


async def fetch_json(client, path):
    r = await client.get(path)
    return r.json()
