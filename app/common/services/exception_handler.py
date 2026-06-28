from fastapi import Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException



def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": {"code": exc.status_code, "message": exc.detail}},
    )


EXCEPTION_HANDLERS = {
    HTTPException: http_exception_handler,
    StarletteHTTPException: http_exception_handler,
}
