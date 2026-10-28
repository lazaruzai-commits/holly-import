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
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

# Server-side fallback when a form is submitted without a chat session id.
# Matches the 4-char Crockford-style alphabet used by static/js/chat.js so
# all Telegram messages quote a uniformly short, easy-to-type code.
# i/l/o/u dropped so 1/0 are unambiguous (32 chars, ~1M combos).
_SID_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"


def _new_session_id() -> str:
    return "".join(secrets.choice(_SID_ALPHABET) for _ in range(4))

import chat_agent
import leads
import telegram_client

log = logging.getLogger("holly.app")

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


def _asset_version() -> str:
    """Short git SHA of the running checkout, used as ?v= on CSS/JS URLs so
    Cloudflare / browsers fetch fresh assets on every deploy. Falls back to
    the stylesheet's mtime when git isn't available."""
    try:
        import subprocess
        sha = subprocess.check_output(
            ["git", "-C", str(Path(__file__).parent), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, timeout=3,
        ).decode().strip()
        if sha:
            return sha
    except Exception:
        pass
    try:
        return str(int((Path(__file__).parent / "static" / "css" / "holly.css").stat().st_mtime))
    except Exception:
        return "1"


ASSET_VERSION = _asset_version()


_STATIC_MTIME: dict[str, str] = {}


def static_v(rel_path: str) -> str:
    """Absolute URL for a static file with a ?v= that changes whenever the file
    on disk does (mtime). Lets replaced model renders / gallery frames bypass
    Cloudflare's edge cache without a manual purge — same idea as the git-SHA
    version on CSS/JS, but per-file so a single swapped PNG is enough."""
    rel = _prefer_webp((rel_path or "").lstrip("/"))
    v = _STATIC_MTIME.get(rel)
    if v is None:
        try:
            v = str(int((PROJECT_ROOT / rel).stat().st_mtime))
        except OSError:
            v = ASSET_VERSION
        _STATIC_MTIME[rel] = v
    return f"{ROOT_PATH}/{rel}?v={v}"


_WEBP_FOR: dict[str, str] = {}


def _prefer_webp(rel: str) -> str:
    """`static/img/x.png` -> `static/img/x.webp` when that sibling exists.

    scripts/make_webp.py writes a down-sized WebP next to every PNG/JPG
    (typically 5-15x smaller). Data files and templates keep naming the
    original; the swap happens here so one place covers cards, galleries,
    brand images and the JSON API alike.
    """
    hit = _WEBP_FOR.get(rel)
    if hit is None:
        hit = rel
        if rel.lower().endswith((".png", ".jpg", ".jpeg")):
            cand = PROJECT_ROOT / (rel.rsplit(".", 1)[0] + ".webp")
            if cand.is_file():
                hit = cand.relative_to(PROJECT_ROOT).as_posix()
        _WEBP_FOR[rel] = hit
    return hit


templates.env.globals["static_v"] = static_v

SITE = {
    "name": os.environ.get("SITE_NAME", "Holly Import"),
    "location": os.environ.get("SITE_LOCATION", "Los Palos Grandes, Caracas"),
    "phone": os.environ.get("SITE_PHONE", ""),
    "whatsapp": os.environ.get("SITE_WHATSAPP", ""),
    "telegram_handle": "@HollyImportBot",
    "instagram_handle": os.environ.get("SITE_INSTAGRAM_HANDLE", "hollyimport"),
    "instagram_widget_url": os.environ.get("INSTAGRAM_WIDGET_URL", "").strip(),
}

# Third-party analytics — both optional. Nothing loads until the ID is set.
ANALYTICS = {
    "gtm_id": os.environ.get("GTM_CONTAINER_ID", "").strip(),      # e.g. GTM-XXXXXXX (preferred: manages GA4 + Meta)
    "ga_id": os.environ.get("GA_MEASUREMENT_ID", "").strip(),      # e.g. G-XXXXXXXXXX (direct gtag, if not using GTM)
    "meta_pixel_id": os.environ.get("META_PIXEL_ID", "").strip(),  # e.g. 1234567890 (direct pixel, if not via GTM)
}

# Attribution fields accepted from the browser (see static/js/analytics.js) and
# persisted with every lead / service booking.
ATTRIBUTION_KEYS = (
    "visitor_id", "first_source", "first_medium", "first_campaign", "first_referrer", "first_landing",
    "last_source", "last_medium", "last_campaign", "last_content", "last_term",
    "gclid", "fbclid", "page",
)


def _clean_attribution(raw: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {k: str(raw.get(k, "") or "")[:200] for k in ATTRIBUTION_KEYS}

app = FastAPI(title="Holly Import")
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")


@app.middleware("http")
async def _static_cache_headers(request: Request, call_next):
    """Every static URL the templates emit carries a ?v= stamp (git SHA for
    CSS/JS, file mtime for images/video), so the bytes behind a given URL never
    change: browsers and Cloudflare may keep them for a year. Un-stamped static
    URLs get a day. HTML responses are left alone (no-store semantics apply)."""
    response = await call_next(request)
    if request.url.path.startswith("/static/") and response.status_code == 200:
        if "v" in request.query_params:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "public, max-age=86400"
    return response


# ---------- data loaders (cached at process start) ----------

def _load_json(name: str) -> dict[str, Any]:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


_MODELS = _load_json("models.json")
_COMPETITORS = _load_json("competitors.json")
_FINANCING = _load_json("financing.json")   # plans for /simulador (edit data/financing.json)


def _promote_to_png_if_available(models: list[dict[str, Any]]) -> None:
    """Swap any model's `image` to its .png sibling when one exists on disk.

    JSON canonical paths stay `.jpg`; dropping a `<id>.png` into
    static/img/models/ silently upgrades the gallery to the higher-fidelity
    dealership render. Falls back to whatever the JSON specifies if no
    PNG is present.
    """
    img_dir = PROJECT_ROOT / "static" / "img" / "models"
    for m in models:
        png = img_dir / f"{m['id']}.png"
        if png.is_file():
            m["image"] = f"static/img/models/{m['id']}.png"


_promote_to_png_if_available(_MODELS["models"])


def models_list() -> list[dict[str, Any]]:
    return _MODELS["models"]


def _build_inventory() -> list[dict[str, Any]]:
    """Physical units in stock (data/inventory.json), enriched from the model
    they reference: image / bodyType / tagline / specs fall back to the model
    unless the unit overrides them. Units with no modelId (discontinued
    models still in stock) must carry their own specs."""
    try:
        raw = _load_json("inventory.json").get("units", [])
    except FileNotFoundError:
        return []
    by_id = {m["id"]: m for m in models_list()}
    out: list[dict[str, Any]] = []
    for u in raw:
        if u.get("status", "disponible") != "disponible":
            continue
        m = by_id.get(u.get("modelId") or "")
        unit = {
            "image": (m or {}).get("image", ""),
            "bodyType": (m or {}).get("bodyType", ""),
            "tagline": (m or {}).get("tagline", ""),
            "specs": (m or {}).get("specs", {}),
            "detailUrl": f"/modelos/{m['id']}" if m else "",
            **u,
        }
        out.append(unit)
    return out


_INVENTORY = _build_inventory()


def inventory_units() -> list[dict[str, Any]]:
    return _INVENTORY


def passenger_models() -> list[dict[str, Any]]:
    """MG + Maxus cars, SUVs and pickups shown on /modelos (category==passenger)."""
    return [m for m in models_list() if m.get("category", "passenger") == "passenger"]


def commercial_models() -> list[dict[str, Any]]:
    """Cargo trucks (S80, C300) shown on /comerciales."""
    return [m for m in models_list() if m.get("category") == "comercial"]


def imported_models() -> list[dict[str, Any]]:
    """Imported other-brand vehicles (Toyota, Kia, Peugeot…) shown on /importados."""
    return [m for m in models_list() if m.get("category") == "importado"]


def model_by_id(mid: str) -> dict[str, Any] | None:
    for m in models_list():
        if m["id"] == mid:
            return m
    return None


# ---------- template context helper ----------

def _ctx(request: Request, **extra) -> dict[str, Any]:
    # `models` defaults to the passenger lineup so /modelos and any lookup
    # driven from the header context stay clean; /comerciales overrides it.
    base = {
        "request": request,
        "root_path": ROOT_PATH,
        "asset_v": ASSET_VERSION,
        "site": SITE,
        "analytics": ANALYTICS,
        "models": passenger_models(),
        "brands": ["MG", "Maxus"],
    }
    base.update(extra)
    return base


# ---------- pages ----------

def _slide(sid: str, model: dict[str, Any] | None) -> dict[str, Any]:
    """Hero slide. Uses the web encode (`<id>-720p.mp4`, ~1-4 MB) produced by
    scripts/encode_hero_videos.sh when it exists, else the original upload, and
    the poster frame it extracts so the slide paints before any video arrives."""
    video_dir = PROJECT_ROOT / "static" / "video"
    video = f"static/video/{sid}-720p.mp4" if (video_dir / f"{sid}-720p.mp4").is_file() else f"static/video/{sid}.mp4"
    poster = f"static/video/posters/{sid}.jpg" if (video_dir / "posters" / f"{sid}.jpg").is_file() else ""
    return {"id": sid, "video": video, "poster": poster, "model": model}


@app.get("/simulador", response_class=HTMLResponse)
async def page_simulador(request: Request, modelo: str = ""):
    """Payment simulator: price + plan -> instalment table, computed client-side
    from data/financing.json. `?modelo=<id>` preselects a model."""
    options = [{"id": m["id"], "brand": m["brand"],
                "name": m["name"] if m["name"].lower().startswith(m["brand"].lower()) else f"{m['brand']} {m['name']}",
                "price": m.get("price"), "promo": bool(m.get("promoEligible"))} for m in models_list()]
    return templates.TemplateResponse(
        request, "simulador.html",
        _ctx(request, page="simulador", financing=_FINANCING, options=options,
             preselect=modelo if any(o["id"] == modelo for o in options) else ""),
    )


@app.get("/", response_class=HTMLResponse)
async def page_inicio(request: Request):
    featured = [m for m in models_list() if m["id"] in
                ("mg-rx9", "mg-gt", "maxus-t70-pro-4x4", "mg-zs", "maxus-d90", "mg-cyberster")]
    by_id = {m["id"]: m for m in models_list()}
    # Hero slider — videos sorted lightest first so the page becomes interactive
    # quickly and heavier clips finish buffering while the user watches the first one.
    # Generic "hero" slide (no model) fronts a Holly Import brand intro.
    slides = [_slide(sid, by_id.get(sid)) for sid in ("mg-3", "mg-rx9", "mg-rx5", "hero", "mg-5")]
    # Imported-vehicle spotlight under the hero (currently the Corolla Cross).
    spotlight = model_by_id("toyota-corolla-cross")
    return templates.TemplateResponse(
        request, "inicio.html",
        _ctx(request, page="inicio", featured=featured, slides=slides,
             spotlight=spotlight, inventory=inventory_units()),
    )


@app.get("/inventario", response_class=HTMLResponse)
async def page_inventario(request: Request):
    return templates.TemplateResponse(
        request, "inventario.html",
        _ctx(request, page="inventario", inventory=inventory_units()),
    )


@app.get("/modelos", response_class=HTMLResponse)
async def page_modelos(request: Request):
    return templates.TemplateResponse(
        request, "modelos.html", _ctx(request, page="modelos"),
    )


@app.get("/comerciales", response_class=HTMLResponse)
async def page_comerciales(request: Request):
    return templates.TemplateResponse(
        request, "comerciales.html",
        _ctx(request, page="comerciales", models=commercial_models()),
    )


@app.get("/importados", response_class=HTMLResponse)
async def page_importados(request: Request):
    return templates.TemplateResponse(
        request, "importados.html",
        _ctx(request, page="importados", models=imported_models()),
    )


@app.get("/modelos/{model_id}", response_class=HTMLResponse)
async def page_modelo_detail(request: Request, model_id: str):
    m = model_by_id(model_id)
    if not m:
        raise HTTPException(404, "Modelo no encontrado")
    competitors = []
    for cid in m.get("competitors", []):
        c = _COMPETITORS["competitors"].get(cid)
        if c:
            competitors.append({"id": cid, **c})
    # "También te puede interesar" — same brand or shared category tag,
    # excluding the current model.
    tags = set(m.get("tags", []))
    related = []
    for x in models_list():
        if x["id"] == m["id"]:
            continue
        if x["brand"] == m["brand"] or (set(x.get("tags", [])) & tags):
            related.append(x)
    related = related[:4]
    return templates.TemplateResponse(
        request, "modelo.html",
        _ctx(request, page="modelos",
             model=m, competitors=competitors, related=related),
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

def _with_image_url(m: dict[str, Any]) -> dict[str, Any]:
    """Model dict + a cache-busted absolute `imageUrl` for client-side rendering."""
    return {**m, "imageUrl": static_v(m.get("image", ""))}


@app.get("/api/models")
async def api_models():
    return {"models": [_with_image_url(m) for m in models_list()]}


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
    return {"model": _with_image_url(m), "competitors": competitors}


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
    attribution: dict[str, Any] | None = None

    @field_validator("contact_pref")
    @classmethod
    def _valid_pref(cls, v: str) -> str:
        if v not in ("call_text", "text_only"):
            return "call_text"
        return v


@app.post("/api/lead")
async def api_lead(req: LeadRequest):
    sid = req.session_id or _new_session_id()
    m = model_by_id(req.model_id) if req.model_id else None
    # Inventory units can be asked about directly (ids start with "inv-");
    # resolve those to the unit so the Telegram lead names the actual car.
    unit = next((u for u in inventory_units() if u["id"] == req.model_id), None) if req.model_id else None
    if unit:
        model_name = f"{unit['name']} {unit.get('trim','')} · {unit['color']} (en inventario)".replace("  ", " ")
        brand = unit["brand"]
    else:
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
        attribution=_clean_attribution(req.attribution),
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
    attribution: dict[str, Any] | None = None

    @field_validator("contact_pref")
    @classmethod
    def _valid_pref(cls, v: str) -> str:
        if v not in ("call_text", "text_only"):
            return "call_text"
        return v


@app.post("/api/service")
async def api_service(req: ServiceRequest):
    sid = req.session_id or _new_session_id()
    row = leads.save_service(
        session_id=sid,
        name=req.name.strip(),
        phone=req.phone.strip(),
        contact_pref=req.contact_pref,
        vehicle=req.vehicle.strip(),
        preferred_date=req.preferred_date.strip(),
        preferred_time=req.preferred_time.strip(),
        notes=req.notes.strip(),
        attribution=_clean_attribution(req.attribution),
    )
    await telegram_client.notify_service(row)
    return {"ok": True, "session_id": sid}


# ---------- API: chat inbox (asesor replies coming back from Telegram) ----------

@app.get("/api/chat/inbox")
async def api_chat_inbox(session_id: str, since: str = ""):
    """Long-poll endpoint the open chat panel hits every few seconds.

    `since` is the ISO timestamp of the last asesor message the client has
    already rendered (empty string on first call → only future messages
    are returned). Response always includes `now` so the client can pass it
    back as the next `since`.
    """
    if not (4 <= len(session_id) <= 64):
        raise HTTPException(400, "bad session_id")
    msgs = leads.read_chat_inbox(session_id, since_ts=since or _now_iso())
    return {
        "messages": [{"ts": m["ts"], "content": m["content"]} for m in msgs],
        "now": _now_iso(),
    }


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- API: Telegram inbound webhook ----------

@app.post("/api/telegram-webhook")
async def api_telegram_webhook(
    req: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    """Receives reply messages from the asesor's Telegram and routes them
    back into the originating web chat session.

    Setup: after deploy, register the webhook once:
        curl -F "url=https://andyluciani.com/holly/api/telegram-webhook" \\
             -F "secret_token=$TELEGRAM_WEBHOOK_SECRET" \\
             https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook
    """
    expected = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if not expected:
        # Refuse to operate without a secret — anyone could otherwise inject
        # asesor messages into transcripts.
        raise HTTPException(503, "webhook not configured")
    if x_telegram_bot_api_secret_token != expected:
        raise HTTPException(401, "bad secret")

    update = await req.json()
    msg = update.get("message") or update.get("edited_message") or {}
    chat = msg.get("chat") or {}
    text = (msg.get("text") or "").strip()
    reply_to = msg.get("reply_to_message") or {}
    quoted_text = reply_to.get("text") or ""

    expected_chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if expected_chat and str(chat.get("id")) != expected_chat:
        log.info("ignoring update from unexpected chat_id=%s", chat.get("id"))
        return {"ok": True}

    if not text or not quoted_text:
        # Bare message with no quoted notification — nothing to route.
        return {"ok": True}

    sid = telegram_client.extract_session_id(quoted_text)
    if not sid:
        await telegram_client.send_telegram(
            "⚠️ No pude identificar la sesión. Usa <b>Reply</b> sobre la "
            "notificación original del bot para que pueda enrutar tu "
            "mensaje al chat del cliente.",
            reply_to_message_id=msg.get("message_id"),
        )
        return {"ok": True}

    sender = msg.get("from") or {}
    asesor_label = (sender.get("first_name") or "Asesor").strip()
    leads.save_chat_message(
        session_id=sid,
        role="asesor",
        content=text,
        context=f"telegram:{asesor_label}",
    )
    await telegram_client.send_telegram(
        f"✅ Enviado al chat <code>{sid}</code>.",
        reply_to_message_id=msg.get("message_id"),
    )
    return {"ok": True}


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
        "telegram_webhook_configured": bool(
            os.environ.get("TELEGRAM_WEBHOOK_SECRET")
        ),
        "openrouter_configured": bool(os.environ.get("OPENROUTER_API_KEY")),
        "gtm_configured": bool(ANALYTICS["gtm_id"]),
        "ga4_configured": bool(ANALYTICS["ga_id"]),
        "meta_pixel_configured": bool(ANALYTICS["meta_pixel_id"]),
    }
