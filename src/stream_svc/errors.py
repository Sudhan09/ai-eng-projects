from fastapi.responses import JSONResponse


def envelope(code, message, request_id, details=None):
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            "details": details or [],
        }
    }


def error_response(request, status, code, message):
    request_id = request.state.request_id
    return JSONResponse(
        envelope(code, message, request_id),
        status_code=status,
        headers={"X-Request-ID": request_id},
    )
