import asyncio

from test_w04_part5_settings import KEY, MATRIX, URL, use_env  # Step 5.1's names

from aiofetch.client import AiofetchClient
from aiofetch.fake import FakeTransport
from aiofetch.settings import Settings


def test_the_client_built_from_settings_sends_the_key(monkeypatch):
    use_env(monkeypatch, MATRIX["valid"])
    client = AiofetchClient.from_settings(Settings(_env_file=None))
    assert client.transport.client.headers["authorization"] == f"Bearer {KEY}"


# my own, for the flowmap: settings in, a client on a fake, item 7 out
def test_a_client_from_settings_fetches_item_7_on_a_fake():
    settings = Settings(_env_file=None, base_url=URL, api_key=KEY, attempts=2)
    fake = FakeTransport({"/items/7": {"id": "7"}})

    async def main():
        async with AiofetchClient.from_settings(settings, transport=fake) as client:
            return await client.get_json("/items/7"), client.attempts

    assert asyncio.run(main()) == ({"id": "7"}, 2)
