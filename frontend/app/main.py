from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    backend_url: str = "http://backend:8000"


settings = Settings()
app = FastAPI(title="Dev Stack Frontend")


class HealthPayload(BaseModel):
    status: str


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    context = {"request": request, "health": None, "error": None}
    try:
        async with httpx.AsyncClient(base_url=settings.backend_url, timeout=5.0) as client:
            response = await client.get("/health")
            response.raise_for_status()
            context["health"] = response.json()
    except Exception as exc:  # pragma: no cover - runtime safeguard
        context["error"] = str(exc)
    return templates.TemplateResponse("index.html", context)


@app.get("/health", response_class=JSONResponse)
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})
