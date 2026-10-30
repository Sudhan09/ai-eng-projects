from fastapi import Depends, FastAPI, HTTPException

from stream_svc.deps import get_authed_source
from stream_svc.models import (
    MODELS,
    GenerateRequest,
    GenerateResponse,
    HealthStatus,
    ModelInfo,
)

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
    return app

