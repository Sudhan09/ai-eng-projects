from aiofetch.errors import CircuitOpenError, TransientError
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


def envelope(code, message, request_id, details=None):
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            "details": details or [],
        }
    }


def error_response(request, status, code, message, details=None, retry_after=None):
    request_id = request.state.request_id
    headers = {"X-Request-ID": request_id}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(
        envelope(code, message, request_id, details),
        status_code=status,
        headers=headers,
    )


class AppError(Exception):
    status = 500
    code = "internal_error"
    message = "Something went wrong on our side."

    def __init__(self, message=None, retry_after=None):
        if message is not None:
            self.message = message
        self.retry_after = retry_after
        super().__init__(self.message)


class AuthError(AppError):
    status = 401
    code = "unauthorized"
    message = "A valid API key is required."


class ModelNotFound(AppError):
    status = 404
    code = "model_not_found"
    message = "No model has that id."


class UpstreamFailed(AppError):
    status = 502
    code = "upstream_error"
    message = "The model provider sent a bad answer."


class UpstreamBusy(AppError):
    status = 503
    code = "upstream_busy"
    message = "The model provider is busy. Try again later."


class UpstreamTimeout(AppError):
    status = 504
    code = "upstream_timeout"
    message = "The model provider didn't answer in time."


def from_fetch_error(exc, retry_after):
    if isinstance(exc, TransientError) and exc.reason.startswith("timeout"):
        return UpstreamTimeout()
    if isinstance(exc, TransientError):
        if exc.retry_after is not None:
            retry_after = round(exc.retry_after)
        return UpstreamBusy(retry_after=retry_after)
    if isinstance(exc, CircuitOpenError):
        return UpstreamBusy(retry_after=retry_after)
    return UpstreamFailed()


async def app_error(request, exc):
    return error_response(
        request, exc.status, exc.code, exc.message, retry_after=exc.retry_after
    )


async def validation_error(request, exc):
    problems = exc.errors()
    for problem in problems:
        if problem["type"] == "json_invalid":
            return error_response(
                request, 400, "malformed_json", "The request body isn't valid JSON."
            )
    details = []
    for problem in problems:
        field = ".".join(str(part) for part in problem["loc"])
        details.append({"field": field, "problem": problem["msg"]})
    return error_response(
        request, 422, "validation_error", "The request doesn't match the API.", details
    )


async def http_error(request, exc):
    codes = {404: "not_found", 405: "method_not_allowed"}
    code = codes.get(exc.status_code, "http_error")
    return error_response(request, exc.status_code, code, exc.detail)


def install(app):
    app.add_exception_handler(AppError, app_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(HTTPException, http_error)
