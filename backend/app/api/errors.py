"""Unified error body: {"error": {"category", "message", "detail"}} with Chinese messages (B8)."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..domain.tickers import TickerFormatError
from ..providers.base import DataFetchError
from ..services.watchlist import WatchlistError

NOT_FOUND = {"not_found", "ticker_or_data_unavailable", "ths_financials_empty", "yahoo_financials_empty"}
BAD_REQUEST = {"invalid_date_range", "unsupported_currency", "not_supported"}
HTTP_MESSAGES = {404: "接口不存在", 405: "请求方法不被允许"}


def body(category: str, message: str, detail: str | None = None) -> dict:
    return {"error": {"category": category, "message": message, "detail": detail}}


def install(app: FastAPI) -> None:
    @app.exception_handler(DataFetchError)
    def _data(_: Request, error: DataFetchError):
        status = 404 if error.category in NOT_FOUND else 400 if error.category in BAD_REQUEST else 502
        return JSONResponse(body(error.category, error.message, error.detail), status_code=status)

    @app.exception_handler(TickerFormatError)
    def _ticker(_: Request, error: TickerFormatError):
        return JSONResponse(body("invalid_ticker", str(error)), status_code=400)

    @app.exception_handler(WatchlistError)
    def _watchlist(_: Request, error: WatchlistError):
        return JSONResponse(body(error.category, error.message), status_code=error.status)

    @app.exception_handler(ValueError)
    def _value(_: Request, error: ValueError):
        return JSONResponse(body("invalid_request", str(error)), status_code=400)

    @app.exception_handler(RequestValidationError)
    def _validation(_: Request, error: RequestValidationError):
        fields = "、".join(".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]) for e in error.errors())
        return JSONResponse(body("invalid_request", f"请求参数不正确：{fields}", str(error.errors())), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    def _http(_: Request, error: StarletteHTTPException):
        message = error.detail if isinstance(error.detail, str) and error.detail not in {"Not Found", "Method Not Allowed"} \
            else HTTP_MESSAGES.get(error.status_code, "请求失败")
        return JSONResponse(body("http_error", message), status_code=error.status_code)
