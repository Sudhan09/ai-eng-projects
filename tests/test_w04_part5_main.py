import asyncio
import os
import subprocess
import sys

from test_w04_part5_settings import AIOFETCH_VARS, KEY, MATRIX, URL, use_env  # Step 5.1's names

from aiofetch.__main__ import main
from aiofetch.client import AiofetchClient
from aiofetch.flaky import FlakyAPI
from aiofetch.settings import get_settings


def test_bad_config_stops_the_command_before_any_request(tmp_path):
    env = {name: os.environ[name] for name in os.environ if name not in AIOFETCH_VARS}
    env |= {"AIOFETCH_BASE_URL": URL, "AIOFETCH_API_KEY": KEY, "AIOFETCH_TIMEOUT": "0"}
    run = subprocess.run(
        [sys.executable, "-m", "aiofetch", "/v2/items/7"],
        cwd=tmp_path,  # a folder with no .env in it
        env=env,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 2 and run.stdout == ""
    assert run.stderr.startswith("aiofetch: bad config:") and "timeout" in run.stderr


# my own: on a fake, exit 0 when every path works and 1 when any fails
def test_main_exits_0_when_all_work_and_1_when_any_fails(monkeypatch, capsys):
    use_env(monkeypatch, MATRIX["valid"])
    get_settings.cache_clear()
    real = AiofetchClient.from_settings.__func__

    def on_a_fake(cls, settings, *, transport=None):
        return real(cls, settings, transport=FlakyAPI(script={"/items/2": [404]}))

    monkeypatch.setattr(AiofetchClient, "from_settings", classmethod(on_a_fake))
    assert asyncio.run(main(["/items/1"])) == 0
    assert asyncio.run(main(["/items/2"])) == 1
    printed = capsys.readouterr().out.splitlines()
    assert '"value": {"id": "1", "name": "item 1"}' in printed[0]
    assert '"error": "/items/2: 404 Not Found"' in printed[1]
    get_settings.cache_clear()
