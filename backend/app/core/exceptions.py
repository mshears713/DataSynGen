from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, message: str, detail: str = "", status_code: int = 500):
        self.message = message
        self.detail = detail
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            message=f"{resource} not found",
            detail=f"{resource} with id '{resource_id}' does not exist",
            status_code=404,
        )


class ConfigError(AppError):
    def __init__(self, message: str, detail: str = ""):
        super().__init__(message=message, detail=detail, status_code=422)


class RunStateError(AppError):
    def __init__(self, message: str, detail: str = ""):
        super().__init__(message=message, detail=detail, status_code=409)


class LLMCallError(AppError):
    def __init__(self, message: str, detail: str = "", retryable: bool = True):
        super().__init__(message=message, detail=detail, status_code=502)
        self.retryable = retryable


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": type(exc).__name__,
            "message": exc.message,
            "detail": exc.detail,
        },
    )
