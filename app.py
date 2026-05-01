"""Holly Import — FastAPI backend.

Run locally:
    uvicorn app:app --reload --port 8000
Then open http://localhost:8000

In production behind nginx at andyluciani.com/holly, set APP_ROOT_PATH=/holly
in the environment so templates emit prefixed asset/api URLs.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

import chat_agent
import leads
import telegram_client

load_dotenv(override=False)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))

# Subpath prefix when reverse-proxied (e.g. "/holly"). Templates use this
# to build asset and API URLs so the same code works at "/" locally and
# under "/holly" in production.
ROOT_PATH = os.environ.get("APP_ROOT_PATH", "").rstrip("/")

SITE = {
    "name": os.environ.get("SITE_NAME", "Holly Import"),
    "location": os.environ.get("SITE_LOCATION", "Los Palos Grandes, Caracas"),
    "phone": os.environ.get("SITE_PHONE", ""),
    "whatsapp": os.environ.get("SITE_WHATSAPP", ""),
    "telegram_handle": "@HollyImportBot",
}

app = FastAPI(title="Holly Import")
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")


# ---------- data loaders (cached at process start) ----------

def _load_json(name: str) -> dict[str, Any]:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


_MODELS = _load_json("models.json")
_COMPETITORS = _load_json("competitors.json")


def models_list() -> list[dict[str, Any]]:
    return _MODELS["models"]


def model_by_id(mid: str) -> dict[str, Any] | None:
    for m in models_list():
        if m["id"] == mid:
            return m
    return None


# ---------- template context helper ----------

def _ctx(request: Request, **extra) -> dict[str, Any]:
    base = {
        "request": request,
        "root_path": ROOT_PATH,
        "site": SITE,
        "models": models_list(),
        "brands": ["MG", "Maxus"],
    }
    base.update(extra)
    return base


# ---------- pages ----------

@app.get("/", response_class=HTMLResponse)
async def page_inicio(request: Request):
    featured = [m for m in models_list() if m["id"] in
                ("mg-rx9", "mg-3-hybrid", "maxus-t90", "mg-zs", "maxus-d90", "mg-cyberster")]
    by_id = {m["id"]: m for m in models_list()}
    # Hero slider — videos sorted lightest first so the page becomes interactive
    # quickly and heavier clips finish buffering while the user watches the first one.
    # Generic "hero" slide (no model) fronts a Holly Import brand intro.
    slides = [
        {"id": "mg-3",   "video": "static/video/mg-3.mp4",   "model": by_id.get("mg-3")},
        {"id": "mg-rx9", "video": "static/video/mg-rx9.mp4", "model": by_id.get("mg-rx9")},
        {"id": "mg-rx5", "video": "static/video/mg-rx5.mp4", "model": by_id.get("mg-rx5")},
        {"id": "hero",   "video": "static/video/hero.mp4",   "model": None},
        {"id": "mg-5",   "video": "static/video/mg-5.mp4",   "model": by_id.get("mg-5")},
    ]
    return templates.TemplateResponse(
        request, "inicio.html",
        _ctx(request, page="inicio", featured=featured, slides=slides),
    )


@app.get("/modelos", response_class=HTMLResponse)
async def page_modelos(request: Request):
    return templates.TemplateResponse(
        request, "modelos.html", _ctx(request, page="modelos"),
    )


@app.get("/comparar", response_class=HTMLResponse)
async def page_comparar(request: Request):
    return templates.TemplateResponse(
        request, "comparar.html", _ctx(request, page="comparar"),
    )


@app.get("/servicio", response_class=HTMLResponse)
async def page_servicio(request: Request):
    return templates.TemplateResponse(
        request, "servicio.html", _ctx(request, page="servicio"),
    )


@app.get("/repuestos", response_class=HTMLResponse)
async def page_repuestos(request: Request):
    return templates.TemplateResponse(
        request, "repuestos.html", _ctx(request, page="repuestos"),
    )


@app.get("/promocion", response_class=HTMLResponse)
async def page_promocion(request: Request):
    promo_models = [m for m in models_list() if m.get("promoEligible")]
    return templates.TemplateResponse(
        request, "promocion.html",
        _ctx(request, page="promocion", promo_models=promo_models),
    )


@app.get("/contacto", response_class=HTMLResponse)
async def page_contacto(request: Request):
    return templates.TemplateResponse(
        request, "contacto.html", _ctx(request, page="contacto"),
    )


# ---------- API: data ----------

@app.get("/api/models")
async def api_models():
    return {"models": models_list()}


@app.get("/api/models/{model_id}")
async def api_model_detail(model_id: str):
    m = model_by_id(model_id)
    if not m:
        raise HTTPException(404, "Modelo no encontrado")
    competitors = []
    for cid in m.get("competitors", []):
        c = _COMPETITORS["competitors"].get(cid)
        if c:
            competitors.append({"id": cid, **c})
    return {"model": m, "competitors": competitors}


@app.get("/api/compare")
async def api_compare(holly: str, competitor: str):
    m = model_by_id(holly)
    if not m:
        raise HTTPException(404, "Modelo Holly no encontrado")
    c = _COMPETITORS["competitors"].get(competitor)
    if not c:
        raise HTTPException(404, "Competidor no encontrado")
    return {"holly": m, "competitor": {"id": competitor, **c}}


# ---------- API: chat ----------

class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=4, max_length=64)
    messages: list[ChatMessage] = Field(min_length=1, max_length=30)
    context: str = Field(default="", max_length=300)


@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    last_user = next(
        (m for m in reversed(req.messages) if m.role == "user"), None
    )
    if not last_user:
        raise HTTPException(400, "Falta mensaje del usuario")

    leads.save_chat_message(
        session_id=req.session_id,
        role="user",
        content=last_user.content,
        context=req.context,
    )

    history = [{"role": m.role, "content": m.content} for m in req.messages]
    reply, err = await chat_agent.chat(history, context_note=req.context)

    leads.save_chat_message(
        session_id=req.session_id,
        role="assistant",
        content=reply,
        context=req.context,
    )

    # Forward the turn to Telegram (non-blocking failure).
    await telegram_client.notify_chat_turn(
        req.session_id, last_user.content, reply, req.context
    )

    return {"reply": reply, "error": err, "session_id": req.session_id}


# ---------- API: lead capture ----------

class LeadRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)
    flow: str = Field(default="compra", max_length=20)
    brand: str = Field(default="", max_length=20)
    model_id: str = Field(default="", max_length=64)
    name: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=4, max_length=30)
    contact_pref: str = Field(default="call_text")
    notes: str = Field(default="", max_length=500)

    @field_validator("contact_pref")
    @classmethod
    def _valid_pref(cls, v: str) -> str:
        if v not in ("call_text", "text_only"):
            return "call_text"
        return v


@app.post("/api/lead")
async def api_lead(req: LeadRequest):
    sid = req.session_id or secrets.token_hex(8)
    m = model_by_id(req.model_id) if req.model_id else None
    model_name = m["name"] if m else ""
    brand = m["brand"] if m else req.brand

    row = leads.save_lead(
        session_id=sid,
        flow=req.flow,
        brand=brand,
        model_id=req.model_id,
        model_name=model_name,
        name=req.name.strip(),
        phone=req.phone.strip(),
        contact_pref=req.contact_pref,
        notes=req.notes.strip(),
    )
    await telegram_client.notify_lead(row)
    return {"ok": True, "session_id": sid}


# ---------- API: service booking ----------

class ServiceRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=4, max_length=30)
    contact_pref: str = Field(default="call_text")
    vehicle: str = Field(default="", max_length=80)
    preferred_date: str = Field(default="", max_length=20)
    preferred_time: str = Field(default="", max_length=20)
    notes: str = Field(default="", max_length=500)

    @field_validator("contact_pref")
    @classmethod
    def _valid_pref(cls, v: str) -> str:
        if v not in ("call_text", "text_only"):
            return "call_text"
        return v


@app.post("/api/service")
async def api_service(req: ServiceRequest):
    sid = req.session_id or secrets.token_hex(8)
    row = leads.save_service(
        session_id=sid,
        name=req.name.strip(),
        phone=req.phone.strip(),
        contact_pref=req.contact_pref,
        vehicle=req.vehicle.strip(),
        preferred_date=req.preferred_date.strip(),
        preferred_time=req.preferred_time.strip(),
        notes=req.notes.strip(),
    )
    await telegram_client.notify_service(row)
    return {"ok": True, "session_id": sid}


# ---------- health ----------

@app.get("/api/health")
async def api_health():
    return {
        "ok": True,
        "models": len(models_list()),
        "competitors": len(_COMPETITORS["competitors"]),
        "telegram_configured": bool(
            os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")
        ),
        "openrouter_configured": bool(os.environ.get("OPENROUTER_API_KEY")),
    }
