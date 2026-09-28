"""FastAPI application for the Phase 0 health check."""

# BaseModel types the health response.
# FastAPI builds the ASGI application.
from fastapi import FastAPI
from pydantic import BaseModel


# JSON body returned by GET /health.
class HealthResponse(BaseModel):
    """Status payload for the health route."""

    # "ok" when the process is serving requests.
    status: str


# Application object uvicorn loads as spacedesigner.api.main:app.
app = FastAPI(title="PhotoSpace", version="0.1.0")


# Liveness route used by the Phase 0 checks and the Next.js page.
@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report that the API process is up."""
    # Return the only status this skeleton defines.
    return HealthResponse(status="ok")
