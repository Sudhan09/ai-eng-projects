from importlib.resources import files

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from sse_starlette import EventSourceResponse

from stream_svc.deps import get_authed_source
from stream_svc.models import (
    MODELS,
    GenerateRequest,
    GenerateResponse,
    HealthStatus,
    ModelInfo,
)
from stream_svc.stream import frames

VERSION = "0.1.0"

def create_app():
    app = FastAPI(title="stream-svc", version=VERSION)

    @app.get("/health", response_model=HealthStatus)
    async def health():
        return HealthStatus(version=VERSION)


    @app.get("/models/{model_id}", response_model=ModelInfo)
    async def get_model(model_id, verbose: bool = False):
        if model_id not in MODELS:
            raise HTTPException(404, "no model has that id")
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
        prompt=Query(min_length=1),
        max_tokens: int = Query(64, ge=1),
        source=Depends(get_authed_source),
    ):
        return EventSourceResponse(
            frames(source, prompt, max_tokens),
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )

    @app.get("/demo", include_in_schema=False)
    async def demo():
        page = files("stream_svc") / "demo.html"
        return HTMLResponse(page.read_text())
    
    return app



