from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.middleware.sessions import SessionMiddleware

from .gateway import AuthTokens, BackendError, BackendGateway, UnauthorizedError

TEMPLATES_DIR = Path(__file__).parent / "templates"


_PROMPT_CATALOG = [
    {
        "title": "Neon skyline",
        "prompt": (
            "a futuristic neon-lit skyline at dusk, ultra wide angle, "
            "cinematic lighting, volumetric fog"
        ),
        "category": "Futurism",
    },
    {
        "title": "Forest spirits",
        "prompt": (
            "ethereal spirits drifting through an ancient forest, "
            "bioluminescent highlights, studio ghibli style"
        ),
        "category": "Fantasy",
    },
    {
        "title": "Architectural concept",
        "prompt": (
            "minimalist concrete museum atrium flooded with natural light, "
            "brutalist symmetry, ray-traced reflections"
        ),
        "category": "Concept art",
    },
    {
        "title": "Product hero",
        "prompt": (
            "sleek wearable device floating above a rippled water surface, "
            "dramatic rim lighting, product photography"
        ),
        "category": "Product",
    },
    {
        "title": "Editorial portrait",
        "prompt": (
            "editorial portrait of a musician surrounded by floating "
            "musical notes, soft depth of field, warm tones"
        ),
        "category": "Portrait",
    },
    {
        "title": "Nature macro",
        "prompt": (
            "super macro shot of a dew-covered leaf with prismatic refraction, "
            "8k, hyperrealistic"
        ),
        "category": "Nature",
    },
]


_PRICING_PLANS = [
    {
        "code": "basic",
        "name": "Creator",
        "description": "Essential toolkit with fast queue access for solo makers.",
        "price": "9.99",
        "currency": "RUB",
        "features": [
            "2k monthly render credits",
            "HD upscaling",
            "Prompt catalog access",
            "Email support",
        ],
        "badge": "Popular",
    },
    {
        "code": "pro",
        "name": "Studio",
        "description": (
            "Priority rendering, collaboration seats, and automation hooks."
        ),
        "price": "29.99",
        "currency": "RUB",
        "features": [
            "10k monthly render credits",
            "Priority queueing",
            "Webhook callbacks",
            "Slack support",
        ],
        "badge": "New",
    },
    {
        "code": "enterprise",
        "name": "Enterprise",
        "description": (
            "Guaranteed throughput with advanced compliance and premium care."
        ),
        "price": "99.99",
        "currency": "RUB",
        "features": [
            "Unlimited team credits",
            "Dedicated rendering pods",
            "Single sign-on",
            "24/7 incident hotline",
        ],
        "badge": None,
    },
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    backend_url: str = "http://backend:8000"
    backend_ws_url: str | None = None
    session_secret: str = "front-secret-key"
    max_upload_bytes: int = 8 * 1024 * 1024
    prompt_catalog: list[dict[str, str]] = Field(
        default_factory=lambda: list(_PROMPT_CATALOG)
    )


templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
settings = Settings()
app = FastAPI(title="DreamFoundry")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="lax",
)

_gateway = BackendGateway(
    base_url=settings.backend_url, websocket_base_url=settings.backend_ws_url
)
app.state.gateway = _gateway
app.state.settings = settings


def get_gateway() -> BackendGateway:
    return app.state.gateway  # type: ignore[return-value]


def _json_default(value: Any) -> str:
    return str(value)


def _serialise(value: Any) -> Any:
    return json.loads(json.dumps(value, default=_json_default))


def _consume_flash(request: Request) -> list[dict[str, str]]:
    return request.session.pop("_messages", [])


def _flash(request: Request, level: str, message: str) -> None:
    messages = request.session.setdefault("_messages", [])
    messages.append({"level": level, "text": message})


def _get_auth_session(request: Request) -> dict[str, Any] | None:
    auth = request.session.get("auth")
    return auth if isinstance(auth, dict) else None


def _store_auth_session(
    request: Request, tokens: AuthTokens, user_payload: dict[str, Any]
) -> None:
    snapshot = {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "session_id": tokens.session_id,
        "account": _serialise(tokens.user) if tokens.user else None,
        "user": _serialise(user_payload),
        "user_id": user_payload.get("id"),
        "email": user_payload.get("email"),
    }
    request.session["auth"] = snapshot


def _merge_auth_session(
    request: Request,
    *,
    tokens: AuthTokens | None = None,
    user_payload: dict[str, Any] | None = None,
) -> None:
    session = _get_auth_session(request)
    if session is None:
        return
    if tokens is not None:
        session["access_token"] = tokens.access_token
        session["refresh_token"] = tokens.refresh_token
        session["session_id"] = tokens.session_id
        if tokens.user:
            session["account"] = _serialise(tokens.user)
    if user_payload is not None:
        session["user"] = _serialise(user_payload)
        session["user_id"] = user_payload.get("id")
        session["email"] = user_payload.get("email")
    request.session["auth"] = session


def _clear_auth(request: Request) -> None:
    request.session.pop("auth", None)


@app.get("/", response_class=HTMLResponse, name="home")
async def home(
    request: Request, gateway: BackendGateway = Depends(get_gateway)
) -> HTMLResponse:
    messages = _consume_flash(request)
    health: dict[str, Any] | None = None
    error: str | None = None
    try:
        health = await gateway.health()
    except Exception as exc:  # pragma: no cover - defensive
        error = str(exc)
    context = {
        "request": request,
        "messages": messages,
        "health": health,
        "error": error,
        "prompt_catalog": settings.prompt_catalog[:3],
    }
    return templates.TemplateResponse("home.html", context)


@app.get("/login", response_class=HTMLResponse, name="login_page")
async def login_page(request: Request) -> HTMLResponse:
    if _get_auth_session(request):
        return RedirectResponse(
            url=request.url_for("profile"), status_code=status.HTTP_303_SEE_OTHER
        )
    context = {
        "request": request,
        "messages": _consume_flash(request),
        "form_error": None,
        "email": "",
    }
    return templates.TemplateResponse("login.html", context)


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    gateway: BackendGateway = Depends(get_gateway),
    email: str = Form(..., description="Email address"),
    password: str = Form(..., description="Password"),
) -> HTMLResponse:
    messages = _consume_flash(request)
    if _get_auth_session(request):
        return RedirectResponse(
            url=request.url_for("profile"), status_code=status.HTTP_303_SEE_OTHER
        )
    try:
        tokens = await gateway.login(email=email, password=password)
        user_payload, refreshed = await gateway.get_current_user(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
        )
        if refreshed:
            tokens = refreshed
        _store_auth_session(request, tokens, user_payload)
        _flash(request, "success", "Welcome back! Your dashboard is ready.")
        return RedirectResponse(
            url=request.url_for("generate"), status_code=status.HTTP_303_SEE_OTHER
        )
    except BackendError as exc:
        context = {
            "request": request,
            "messages": messages + [{"level": "error", "text": exc.message}],
            "form_error": exc.message,
            "email": email,
        }
        return templates.TemplateResponse(
            "login.html", context, status_code=status.HTTP_400_BAD_REQUEST
        )


@app.post("/logout")
async def logout(
    request: Request, gateway: BackendGateway = Depends(get_gateway)
) -> RedirectResponse:
    auth = _get_auth_session(request)
    refresh_token = auth.get("refresh_token") if auth else None
    if refresh_token:
        try:
            await gateway.logout(refresh_token)
        except BackendError:  # pragma: no cover - best effort
            pass
    _clear_auth(request)
    _flash(request, "success", "You have been signed out.")
    return RedirectResponse(
        url=request.url_for("home"), status_code=status.HTTP_303_SEE_OTHER
    )


@app.get("/profile", response_class=HTMLResponse, name="profile")
async def profile(
    request: Request, gateway: BackendGateway = Depends(get_gateway)
) -> HTMLResponse:
    messages = _consume_flash(request)
    auth = _get_auth_session(request)
    if not auth:
        _flash(request, "info", "Sign in to manage your profile.")
        return RedirectResponse(
            url=request.url_for("login_page"), status_code=status.HTTP_303_SEE_OTHER
        )
    try:
        user_payload, tokens = await gateway.get_current_user(
            access_token=auth["access_token"],
            refresh_token=auth.get("refresh_token"),
        )
        _merge_auth_session(request, tokens=tokens, user_payload=user_payload)
    except UnauthorizedError:
        _clear_auth(request)
        _flash(request, "info", "Your session has expired. Please log in again.")
        return RedirectResponse(
            url=request.url_for("login_page"), status_code=status.HTTP_303_SEE_OTHER
        )
    except BackendError as exc:
        context = {
            "request": request,
            "messages": messages + [{"level": "error", "text": exc.message}],
            "user": auth.get("user", {}),
            "quotas": {},
            "load_error": exc.message,
        }
        return templates.TemplateResponse(
            "profile.html", context, status_code=status.HTTP_502_BAD_GATEWAY
        )

    context = {
        "request": request,
        "messages": messages,
        "user": user_payload,
        "load_error": None,
    }
    return templates.TemplateResponse("profile.html", context)


@app.post("/profile", response_class=HTMLResponse)
async def update_profile(
    request: Request,
    gateway: BackendGateway = Depends(get_gateway),
    first_name: str | None = Form(None),
    last_name: str | None = Form(None),
    phone_number: str | None = Form(None),
    country: str | None = Form(None),
    city: str | None = Form(None),
    telegram_id: str | None = Form(None),
) -> HTMLResponse:
    auth = _get_auth_session(request)
    if not auth:
        _flash(request, "info", "Please sign in to update your profile.")
        return RedirectResponse(
            url=request.url_for("login_page"), status_code=status.HTTP_303_SEE_OTHER
        )

    payload = {
        "first_name": first_name,
        "last_name": last_name,
        "phone_number": phone_number,
        "country": country,
        "city": city,
        "telegram_id": telegram_id,
    }
    filtered = {key: value for key, value in payload.items() if value}
    if not filtered:
        _flash(request, "warning", "Add at least one field before saving.")
        return RedirectResponse(
            url=request.url_for("profile"), status_code=status.HTTP_303_SEE_OTHER
        )

    try:
        _, tokens = await gateway.update_profile(
            access_token=auth["access_token"],
            refresh_token=auth.get("refresh_token"),
            payload=filtered,
        )
        _merge_auth_session(request, tokens=tokens)
        user_payload, refreshed = await gateway.get_current_user(
            access_token=auth["access_token"],
            refresh_token=auth.get("refresh_token"),
        )
        _merge_auth_session(request, tokens=refreshed, user_payload=user_payload)
        _flash(request, "success", "Profile updated successfully.")
        return RedirectResponse(
            url=request.url_for("profile"), status_code=status.HTTP_303_SEE_OTHER
        )
    except BackendError as exc:
        messages = _consume_flash(request)
        context = {
            "request": request,
            "messages": messages + [{"level": "error", "text": exc.message}],
            "user": auth.get("user", {}),
            "load_error": exc.message,
        }
        return templates.TemplateResponse(
            "profile.html", context, status_code=status.HTTP_400_BAD_REQUEST
        )


@app.get("/generate", response_class=HTMLResponse, name="generate")
async def generate_page(
    request: Request, gateway: BackendGateway = Depends(get_gateway)
) -> HTMLResponse:
    messages = _consume_flash(request)
    auth = _get_auth_session(request)
    if not auth:
        _flash(request, "info", "Sign in to enqueue new generations.")
        return RedirectResponse(
            url=request.url_for("login_page"), status_code=status.HTTP_303_SEE_OTHER
        )

    session_user = auth.get("user")
    user_payload: dict[str, Any] = (
        session_user if isinstance(session_user, dict) else {}
    )
    try:
        user_payload, tokens = await gateway.get_current_user(
            access_token=auth["access_token"],
            refresh_token=auth.get("refresh_token"),
        )
        _merge_auth_session(request, tokens=tokens, user_payload=user_payload)
    except BackendError as exc:
        session_user = auth.get("user")
        user_payload = session_user if isinstance(session_user, dict) else {}
        messages.append({"level": "error", "text": exc.message})
    context = {
        "request": request,
        "messages": messages,
        "user": user_payload,
        "prompt_catalog": settings.prompt_catalog,
        "max_upload": settings.max_upload_bytes,
    }
    return templates.TemplateResponse("generate.html", context)


@app.post("/generate", response_class=HTMLResponse)
async def generate_submit(
    request: Request,
    gateway: BackendGateway = Depends(get_gateway),
    prompt: str = Form(...),
    width: str = Form("512"),
    height: str = Form("512"),
    inference_steps: str = Form("30"),
    guidance_scale: str = Form("7.5"),
    seed: str | None = Form(None),
    model: str = Form("stable-diffusion-xl"),
    scheduler: str = Form("ddim"),
    image: UploadFile = File(...),
) -> HTMLResponse:
    messages = _consume_flash(request)
    auth = _get_auth_session(request)
    if not auth:
        _flash(request, "info", "Sign in to create new generations.")
        return RedirectResponse(
            url=request.url_for("login_page"), status_code=status.HTTP_303_SEE_OTHER
        )

    errors: list[str] = []
    prompt_value = prompt.strip()
    if not prompt_value:
        errors.append("Prompt cannot be empty.")

    try:
        width_value = int(width)
        height_value = int(height)
        if not 64 <= width_value <= 2048 or not 64 <= height_value <= 2048:
            errors.append("Dimensions must be between 64 and 2048 pixels.")
    except ValueError:
        errors.append("Width and height must be whole numbers.")
        width_value = 512
        height_value = 512

    try:
        steps_value = int(inference_steps)
        if not 1 <= steps_value <= 200:
            errors.append("Inference steps should be between 1 and 200.")
    except ValueError:
        errors.append("Inference steps must be an integer.")
        steps_value = 30

    try:
        guidance_value = float(guidance_scale)
        if not 0 <= guidance_value <= 50:
            errors.append("Guidance scale must be between 0 and 50.")
    except ValueError:
        errors.append("Guidance scale must be a number.")
        guidance_value = 7.5

    seed_value: int | None = None
    if seed:
        try:
            seed_value = int(seed)
            if seed_value < 0:
                raise ValueError
        except ValueError:
            errors.append("Seed must be a positive integer.")
            seed_value = None

    allowed_types = {"image/png", "image/jpeg"}
    if image.content_type not in allowed_types:
        errors.append("Upload PNG or JPEG files only.")
    content = await image.read()
    if not content:
        errors.append("Select an image to upload.")
    elif len(content) > settings.max_upload_bytes:
        errors.append("Image exceeds the 8MB upload limit.")

    parameters = {
        "width": width_value,
        "height": height_value,
        "inference_steps": steps_value,
        "guidance_scale": guidance_value,
        "seed": seed_value,
        "model": model,
        "scheduler": scheduler,
    }

    if errors:
        context = {
            "request": request,
            "messages": messages + [{"level": "error", "text": msg} for msg in errors],
            "user": auth.get("user", {}),
            "prompt_catalog": settings.prompt_catalog,
            "max_upload": settings.max_upload_bytes,
            "form_values": {
                "prompt": prompt,
                "width": width,
                "height": height,
                "inference_steps": inference_steps,
                "guidance_scale": guidance_scale,
                "seed": seed,
                "model": model,
                "scheduler": scheduler,
            },
        }
        return templates.TemplateResponse(
            "generate.html", context, status_code=status.HTTP_400_BAD_REQUEST
        )

    upload_tuple = (
        image.filename or "upload.png",
        content,
        image.content_type or "image/png",
    )
    try:
        task_payload, tokens = await gateway.create_generation(
            access_token=auth["access_token"],
            refresh_token=auth.get("refresh_token"),
            prompt=prompt_value,
            parameters={
                key: value for key, value in parameters.items() if value is not None
            },
            upload=upload_tuple,
        )
        _merge_auth_session(request, tokens=tokens)
    except BackendError as exc:
        context = {
            "request": request,
            "messages": messages + [{"level": "error", "text": exc.message}],
            "user": auth.get("user", {}),
            "prompt_catalog": settings.prompt_catalog,
            "max_upload": settings.max_upload_bytes,
            "form_values": {
                "prompt": prompt,
                "width": width,
                "height": height,
                "inference_steps": inference_steps,
                "guidance_scale": guidance_scale,
                "seed": seed,
                "model": model,
                "scheduler": scheduler,
            },
        }
        return templates.TemplateResponse(
            "generate.html", context, status_code=status.HTTP_400_BAD_REQUEST
        )

    _flash(
        request,
        "success",
        (
            "Generation task queued: "
            f"{task_payload.get('task_id', task_payload.get('id'))}"
        ),
    )
    return RedirectResponse(
        url=request.url_for("history"), status_code=status.HTTP_303_SEE_OTHER
    )


@app.get("/history", response_class=HTMLResponse, name="history")
async def history(
    request: Request,
    gateway: BackendGateway = Depends(get_gateway),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
) -> HTMLResponse:
    messages = _consume_flash(request)
    auth = _get_auth_session(request)
    if not auth:
        _flash(request, "info", "Sign in to review task history.")
        return RedirectResponse(
            url=request.url_for("login_page"), status_code=status.HTTP_303_SEE_OTHER
        )

    try:
        payload, tokens = await gateway.list_tasks(
            access_token=auth["access_token"],
            refresh_token=auth.get("refresh_token"),
            page=page,
            page_size=page_size,
        )
        _merge_auth_session(request, tokens=tokens)
    except BackendError as exc:
        context = {
            "request": request,
            "messages": messages + [{"level": "error", "text": exc.message}],
            "items": [],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": 0,
                "has_next": False,
            },
        }
        return templates.TemplateResponse(
            "history.html", context, status_code=status.HTTP_502_BAD_GATEWAY
        )

    context = {
        "request": request,
        "messages": messages,
        "items": payload.get("items", []),
        "pagination": payload.get("pagination", {}),
        "page": page,
        "page_size": page_size,
    }
    return templates.TemplateResponse("history.html", context)


@app.get("/pricing", response_class=HTMLResponse, name="pricing")
async def pricing_page(request: Request) -> HTMLResponse:
    context = {
        "request": request,
        "messages": _consume_flash(request),
        "plans": _PRICING_PLANS,
    }
    return templates.TemplateResponse("pricing.html", context)


@app.post("/pricing/checkout")
async def pricing_checkout(
    request: Request,
    gateway: BackendGateway = Depends(get_gateway),
    plan_code: str = Form(...),
) -> RedirectResponse:
    auth = _get_auth_session(request)
    if not auth:
        _flash(request, "info", "Sign in to upgrade your workspace.")
        return RedirectResponse(
            url=request.url_for("login_page"), status_code=status.HTTP_303_SEE_OTHER
        )

    payload = {
        "plan_code": plan_code,
        "success_url": str(request.url_for("history")),
        "cancel_url": str(request.url_for("pricing")),
    }

    try:
        response, tokens = await gateway.create_payment(
            access_token=auth["access_token"],
            refresh_token=auth.get("refresh_token"),
            payload=payload,
        )
        _merge_auth_session(request, tokens=tokens)
    except BackendError as exc:
        _flash(request, "error", exc.message)
        return RedirectResponse(
            url=request.url_for("pricing"), status_code=status.HTTP_303_SEE_OTHER
        )

    confirmation_url = response.get("confirmation_url")
    if confirmation_url:
        return RedirectResponse(
            url=confirmation_url, status_code=status.HTTP_303_SEE_OTHER
        )

    _flash(
        request,
        "success",
        "Payment created. Follow the email instructions to complete your upgrade.",
    )
    return RedirectResponse(
        url=request.url_for("pricing"), status_code=status.HTTP_303_SEE_OTHER
    )


@app.websocket("/ws/tasks/{task_id}")
async def task_updates_ws(
    websocket: WebSocket,
    task_id: str,
    gateway: BackendGateway = Depends(get_gateway),
) -> None:
    await websocket.accept()
    auth = (
        getattr(websocket, "session", {}).get("auth")
        if hasattr(websocket, "session")
        else None
    )
    if not isinstance(auth, dict) or not auth.get("user_id"):
        await websocket.close(code=4401, reason="Not authenticated")
        return
    access_token = auth.get("access_token")
    user_id = auth.get("user_id")
    try:
        async for message in gateway.stream_task_updates(
            user_id=user_id,
            task_id=task_id,
            access_token=access_token,
        ):
            await websocket.send_text(message)
    except UnauthorizedError:
        await websocket.close(code=4403, reason="Task stream unauthorized")
    except BackendError as exc:
        await websocket.send_text(json.dumps({"type": "error", "message": exc.message}))
        await websocket.close(
            code=status.WS_1011_INTERNAL_ERROR, reason="Backend error"
        )
    except WebSocketDisconnect:
        return


@app.get("/api/ui/prompt-catalog", response_class=JSONResponse)
async def prompt_catalog() -> JSONResponse:
    return JSONResponse(content={"items": settings.prompt_catalog})


@app.get("/health", response_class=JSONResponse)
async def healthcheck() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})
