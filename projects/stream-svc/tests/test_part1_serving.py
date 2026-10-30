import httpx2
import pytest

from stream_svc.lab import lab_app
from stream_svc.serving import running


def test_running_serves_the_app_on_a_real_port_then_stops():
    with running(lab_app(delay=0.0)) as url:
        assert url.startswith("http://127.0.0.1:")
        assert httpx2.get(f"{url}/slow_async").json() == {"slept": 0.0}
    with pytest.raises(httpx2.ConnectError):
        httpx2.get(f"{url}/slow_async")


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_running_raises_when_the_server_cannot_start():
    with pytest.raises(RuntimeError, match="the server failed to start"):  # noqa: SIM117
        with running("no_such_module:app"):  # Uvicorn can't import this app
            pass