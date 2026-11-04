import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

from stream_svc.errors import AppError, envelope

log = logging.getLogger("stream_svc")


@dataclass
class StreamRecord:
    request_id: str
    tokens: int = 0
    outcome: str = "running"
    seconds: float = 0.0
    started: float = field(default_factory=time.perf_counter)


def record_stream(app, record):
    app.state.telemetry.append(record)
    log.info(
        "stream %s: %s, %d tokens, %.2fs",
        record.request_id,
        record.outcome,
        record.tokens,
        record.seconds,
    )


async def frames(request, source, prompt, max_tokens, record):
    try:
        async for token in source.stream(prompt, max_tokens):
            if await request.is_disconnected():
                record.outcome = "disconnected"
                log.info("client disconnected after %d tokens", record.tokens)
                return
            record.tokens += 1
            yield {"event": "token", "id": str(record.tokens), "data": token}
        record.outcome = "done"
    except AppError as exc:
        record.outcome = "error"
        log.info("stream failed after %d tokens: %s", record.tokens, exc.code)
        data = envelope(exc.code, exc.message, record.request_id)
        yield {"event": "error", "data": json.dumps(data)}
    except asyncio.CancelledError, GeneratorExit:
        record.outcome = "disconnected"
        log.info("client disconnected after %d tokens", record.tokens)
        raise
    finally:
        record.seconds = time.perf_counter() - record.started
    yield {"event": "done", "data": "[DONE]"}
