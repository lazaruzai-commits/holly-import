"""OpenRouter-backed chat agent for Holly Import's website assistant.

Uses Kimi K2.6 by default (configurable via OPENROUTER_MODEL), with automatic
OpenRouter fallbacks (OPENROUTER_FALLBACK_MODELS) so one slow or retired
provider never leaves visitors with an error.
The agent is told it represents Holly Import, sells MG and Maxus, and is
based in Los Palos Grandes, Caracas. Replies are always in Spanish.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("holly.chat")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "moonshotai/kimi-k2.6"
# Tried in order after the primary. kimi-k2 (the old default) is down to a
# single provider, which timed out in Nov 2026 and showed visitors the
# "inconveniente técnico" fallback.
DEFAULT_FALLBACKS = "moonshotai/kimi-k2.6,anthropic/claude-haiku-4.5"
TIMEOUT_S = 30.0


def _model_chain() -> list[str]:
    """Primary model plus fallbacks, de-duplicated, at most 3 (OpenRouter's limit)."""
    primary = os.environ.get("OPENROUTER_MODEL", "").strip() or DEFAULT_MODEL
    extra = os.environ.get("OPENROUTER_FALLBACK_MODELS", DEFAULT_FALLBACKS)
    chain: list[str] = []
    for m in [primary, *extra.split(",")]:
        m = m.strip()
        if m and m not in chain:
            chain.append(m)
    return chain[:3]
DATA_DIR = Path(__file__).parent / "data"


def _load_models_summary() -> str:
    """Compact text block listing all models + brand. Used in system prompt."""
    try:
        data = json.loads((DATA_DIR / "models.json").read_text(encoding="utf-8"))
    except Exception:
        return ""
    lines = []
    for m in data.get("models", []):
        promo = " (aplica Engánchate con 500)" if m.get("promoEligible") else ""
        lines.append(f"- {m['name']} ({m['brand']}, {m['bodyType']}){promo}")
    # Units physically in stock right now — the agent should mention these
    # when a customer asks what's available for immediate delivery.
    try:
        inv = json.loads((DATA_DIR / "inventory.json").read_text(encoding="utf-8")).get("units", [])
        stock = [u for u in inv if u.get("status", "disponible") == "disponible"]
        if stock:
            lines.append("\nEn inventario ahora mismo (entrega inmediata, una unidad por línea, el color indicado es el único disponible):")
            for u in stock:
                trim = f" {u['trim']}" if u.get("trim") else ""
                lines.append(f"- {u['name']}{trim}, {u['color']}, {u.get('transmission','')}")
    except Exception:
        pass
    return "\n".join(lines)


SYSTEM_PROMPT = """Eres un asesor de ventas y servicio de Holly Import, concesionario autorizado de MG y Maxus en Los Palos Grandes, Caracas, Venezuela.

Reglas:
- Responde siempre en español venezolano, profesional pero cercano.
- Sé conciso (máximo 3 oraciones por respuesta salvo que el cliente pida detalles).
- Refiere al cliente con un asesor humano cuando pregunte por precios exactos, financiamiento o disponibilidad inmediata. Nunca inventes precios.
- La promoción "Engánchate con 500" aplica a varios modelos MG con planes a 6, 9 o 12 meses, hasta 30% de ahorro y elección de 2 colores.
- Holly Import vende MG (vehículos de pasajeros) y Maxus (SUVs, pickups, camiones), y además una línea de vehículos importados de otras marcas (Toyota, Kia, Peugeot) que se entregan con garantía Holly Import.
- El taller atiende toda la línea MG y Maxus y además somos especialistas en servicio y repuestos Toyota (Hilux, Fortuner, Corolla, Yaris, 4Runner, Land Cruiser, etc.). Si preguntan por servicio Toyota, ofrece agendar cita. Los importados son unidades específicas (un solo color por unidad, el que aparece en la web); para disponibilidad y tiempos de entrega refiere a un asesor humano.
- Si el cliente pide algo fuera del alcance (otra marca, comprar usados, asuntos legales) cordialmente redirige al asesor humano.
- Nunca uses emojis. Nunca menciones que eres una IA: te presentas como "asesor de Holly Import".

Modelos disponibles:
{model_list}
"""


def system_message() -> dict[str, str]:
    return {
        "role": "system",
        "content": SYSTEM_PROMPT.format(model_list=_load_models_summary()),
    }


async def chat(messages: list[dict[str, str]],
               context_note: str = "") -> tuple[str, str | None]:
    """Send a chat completion request to OpenRouter.

    `messages` is the user-visible history (role: user|assistant). We prepend
    the system prompt and an optional context_note describing the structured
    state (e.g. "El cliente está interesado en el MG ZS").

    Returns (reply_text, error_or_none). On any failure we return a graceful
    Spanish fallback so the UI keeps moving.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return (
            "Disculpa, en este momento no puedo conectar con el asistente. "
            "Un asesor de Holly Import te contactará en breve.",
            "missing OPENROUTER_API_KEY",
        )
    models = _model_chain()

    payload_messages: list[dict[str, str]] = [system_message()]
    if context_note:
        payload_messages.append({"role": "system", "content": f"Contexto actual: {context_note}"})
    payload_messages.extend(messages)

    payload = {
        # OpenRouter tries these in order when a model or provider fails.
        "models": models,
        "messages": payload_messages,
        "temperature": 0.4,
        "max_tokens": 600,
        # Short conversational replies: no hidden reasoning, which would eat
        # the token budget and add seconds of latency on reasoning models.
        "reasoning": {"enabled": False},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://andyluciani.com/holly",
        "X-Title": "Holly Import",
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            try:
                r = await client.post(OPENROUTER_URL, json=payload, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                # One retry for a dropped connection / slow first byte.
                log.warning("OpenRouter %s, retrying once: %s", type(e).__name__, e)
                r = await client.post(OPENROUTER_URL, json=payload, headers=headers)
        if r.status_code != 200:
            log.warning("OpenRouter %s: %s", r.status_code, r.text[:300])
            return (
                "Disculpa, tuve un problema procesando tu mensaje. "
                "Un asesor humano te contactará pronto.",
                f"openrouter status {r.status_code}",
            )
        data = r.json()
        if data.get("model") and data["model"] != models[0]:
            log.info("OpenRouter answered with fallback model %s", data["model"])
        reply = ((data.get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()
        if not reply:
            return ("¿Podrías reformular tu pregunta? No alcancé a entenderla.", None)
        return (reply, None)
    except Exception as e:
        log.exception("OpenRouter exception")
        return (
            "Disculpa, hay un inconveniente técnico. "
            "Por favor llámanos directamente o un asesor te contactará.",
            str(e),
        )
