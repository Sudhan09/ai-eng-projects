from pydantic import BaseModel, ConfigDict, Field

MAX_PROMPT_CHARS = 4000
MAX_TOKENS = 512


class UpstreamStatus(BaseModel):
    breaker_state: str
    attempts: int
    retries: int


class HealthStatus(BaseModel):
    status: str = "ok"
    version: str
    upstream: UpstreamStatus


class ModelInfo(BaseModel):
    id: str
    context_tokens: int
    notes: str | None = None


MODELS = {
    "tiny-1": ModelInfo(id="tiny-1", context_tokens=4096, notes="fast, for drafts"),
    "tiny-2": ModelInfo(
        id="tiny-2", context_tokens=8192, notes="slower, longer context"
    ),
}


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    max_tokens: int = Field(default=64, ge=1, le=MAX_TOKENS)


class GenerateResponse(BaseModel):
    text: str
    tokens: int


class TokenPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tokens: list[str]
    done: bool
