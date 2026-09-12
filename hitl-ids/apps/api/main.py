"""The demo API service (plan step S10b).

    python -m uvicorn apps.api.main:app --reload      # http://localhost:8000/docs

**The contract is the authority, not this app.** `apps/api/openapi.json` was written at S10a and is
what S11 generates its client from. FastAPI will happily generate a *different* document from these
handlers; where the two disagree, the handlers are wrong. `tests/test_api.py` compares them, so a
disagreement surfaces as a test failure rather than as a broken client three steps later.

**Errors leave through one envelope.** `ApiError` carries a stable code, and the handler below
renders it as the contract's `{"error": {...}}` shape. FastAPI's own validation errors are
translated into the same shape, so a client never has two error paths to write.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api import routes
from apps.api.contract.common import ErrorBody, ErrorResponse
from apps.api.contract.openapi import API_VERSION, DESCRIPTION, openapi_document
from apps.api.deps import ApiError, database_path

#: The Vite dev server. Wide-open CORS would be wrong even in a demo; this is the one origin S11
#: actually runs on, and S18 takes the list from configuration.
DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def create_app(database: str | Path | None = None) -> FastAPI:
    """Build the app. ``database`` overrides the demo database, which is what tests use."""
    app = FastAPI(
        title="HITL IDS demo API",
        version=API_VERSION,
        description=DESCRIPTION,
        docs_url="/docs",
        redoc_url=None,
    )
    if database is not None:
        app.state.database_path = Path(database)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEV_ORIGINS),
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, error: ApiError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content=error.body())

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        """FastAPI's validation errors, in the contract's envelope rather than its own shape."""
        errors = error.errors()
        first = errors[0] if errors else {}
        location = ".".join(str(part) for part in first.get("loc", ())[1:]) or "request"
        return JSONResponse(status_code=400, content=ErrorResponse(
            error=ErrorBody(
                code="VALIDATION_FAILED",
                message=f"{location}: {first.get('msg', 'invalid request')}",
                detail={"errors": [
                    {"field": ".".join(str(p) for p in item.get("loc", ())[1:]),
                     "message": str(item.get("msg"))}
                    for item in errors]},
            )).model_dump(by_alias=True, exclude_none=True))

    app.include_router(routes.router)

    @app.get("/api/health", tags=["dashboard"], include_in_schema=False)
    def health() -> dict[str, object]:
        """Liveness, plus which database is being served — the first thing to check in a demo."""
        configured = getattr(app.state, "database_path", None)
        resolved = Path(configured) if configured else database_path()
        return {"status": "ok", "database": str(resolved), "exists": resolved.exists(),
                "version": API_VERSION}

    return app


def contract_document() -> dict[str, object]:
    """The S10a contract, for comparison against what FastAPI generates from these handlers."""
    return openapi_document()


app = create_app()
