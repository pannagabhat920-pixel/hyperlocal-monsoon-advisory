from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

class AppException(Exception):
    def __init__(self, title: str, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST, error_type: str = "about:blank"):
        self.title = title
        self.detail = detail
        self.status_code = status_code
        self.error_type = error_type

def make_problem_response(status_code: int, title: str, detail: str, instance: str, error_type: str = "about:blank") -> JSONResponse:
    content = {
        "type": error_type,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": instance,
    }
    return JSONResponse(
        status_code=status_code,
        content=content,
        media_type="application/problem+json"
    )

async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return make_problem_response(
        status_code=exc.status_code,
        title=exc.title,
        detail=exc.detail,
        instance=str(request.url.path),
        error_type=exc.error_type
    )

async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return make_problem_response(
        status_code=exc.status_code,
        title=exc.detail if isinstance(exc.detail, str) else "HTTP Error",
        detail=str(exc.detail),
        instance=str(request.url.path),
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return make_problem_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        title="Validation Error",
        detail=str(exc.errors()),
        instance=str(request.url.path),
        error_type="urn:pannaga:error:validation"
    )

async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return make_problem_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        title="Internal Server Error",
        detail="An unexpected error occurred. Please try again later.",
        instance=str(request.url.path),
        error_type="urn:pannaga:error:internal"
    )
