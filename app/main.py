"""FastAPI application entrypoint."""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import get_settings
from app.db import engine
from app.logging_config import configure_logging
from app.routers import auth, dashboard, expenses, payments, persons, receipts

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("udlaeg")

app = FastAPI(title="Udlæg", docs_url=None, redoc_url=None)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[*settings.allowed_hosts_list, "testserver"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(persons.router)
app.include_router(expenses.router)
app.include_router(receipts.router)
app.include_router(payments.router)

Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.exception_handler(HTTPException)
async def auth_redirect_handler(request: Request, exc: HTTPException):
    """Redirect browser navigations to /login instead of a bare 401."""
    if exc.status_code == status.HTTP_401_UNAUTHORIZED and "text/html" in request.headers.get(
        "accept", ""
    ):
        return RedirectResponse(url="/login", status_code=303)
    from fastapi.responses import JSONResponse

    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    db_state = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - only on real DB outage
        db_state = "error"
    return {"status": "ok" if db_state == "ok" else "error", "db": db_state}
