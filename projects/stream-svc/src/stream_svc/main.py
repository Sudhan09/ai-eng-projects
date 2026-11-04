import logging
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from importlib.resources import files

from aiofetch import AiofetchClient
from fastapi import BackgroundTasks, Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sse_starlette import EventSourceResponse

from stream_svc.deps import get_authed_source, get_upstream
from stream_svc.errors import ModelNotFound, error_response, install
from stream_svc.fakes import FakeProvider
from stream_svc.models import (
    MAX_PROMPT_CHARS,
    MAX_TOKENS,
    MODELS,
    GenerateRequest,
    GenerateResponse,
    HealthStatus,
    ModelInfo,
    UpstreamStatus,
)
from stream_svc.settings import get_settings
from stream_svc.stream import StreamRecord, frames, record_stream

VERSION = "0.1.0"

log = logging.getLogger("stream_svc")


async def request_id_middleware(request, call_next):
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled error, request_id=%s", request_id)
        response = error_response(
            request, 500, "internal_error", "Something went wrong on our side."
        )
    ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    log.info(
        "%s %s %d %.1fms request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        ms,
        request_id,
    )
    return response


def create_app(transport=None):
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app):
        provider = transport
        if provider is None and settings.fake_upstream:
            provider = FakeProvider(delay=0.02)
        client = AiofetchClient(
            settings.upstream_url,
            attempts=settings.upstream_attempts,
            timeout=settings.upstream_timeout,
            transport=provider,
        )
        async with client:
            app.state.upstream = client
            app.state.telemetry = deque(maxlen=1000)
            yield

    app = FastAPI(title="stream-svc", version=VERSION, lifespan=lifespan)
    log.setLevel(logging.INFO)
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
        log.addHandler(handler)
    app.middleware("http")(request_id_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    install(app)

    @app.get("/health", response_model=HealthStatus)
    async def health(upstream=Depends(get_upstream)):
        stats = upstream.stats
        return HealthStatus(
            version=VERSION,
            upstream=UpstreamStatus(
                breaker_state=stats.breaker_state,
                attempts=stats.attempts,
                retries=stats.retries,
            ),
        )

    @app.get("/models/{model_id}", response_model=ModelInfo)
    async def get_model(model_id, verbose: bool = False):
        if model_id not in MODELS:
            raise ModelNotFound()
        info = MODELS[model_id]
        if verbose:
            return info
        return info.model_copy(update={"notes": None})

    @app.post("/generate", response_model=GenerateResponse, status_code=200)
    async def generate(body: GenerateRequest, source=Depends(get_authed_source)):
        tokens = []
        async for token in source.stream(body.prompt, body.max_tokens):
            tokens.append(token)
        return GenerateResponse(text="".join(tokens).strip(), tokens=len(tokens))

    @app.get("/generate/stream", response_class=EventSourceResponse)
    async def generate_stream(
        request: Request,
        background: BackgroundTasks,
        prompt: str = Query(min_length=1, max_length=MAX_PROMPT_CHARS),
        max_tokens: int = Query(64, ge=1, le=MAX_TOKENS),
        source=Depends(get_authed_source),
    ):
        record = StreamRecord(request_id=request.state.request_id)
        background.add_task(record_stream, app, record)
        return EventSourceResponse(
            frames(request, source, prompt, max_tokens, record),
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            background=background,
            ping=settings.heartbeat_seconds,
        )

    @app.get("/demo", include_in_schema=False)
    async def demo():
        page = files("stream_svc") / "demo.html"
        return HTMLResponse(page.read_text())

    return app
