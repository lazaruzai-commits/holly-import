"""Telegram Bot API forwarder + reply parser.

Used to push every captured lead, service booking, and free-text chat turn
to https://t.me/HollyImportBot so a human can follow up. Failures are
non-fatal — we log and continue (the CSV is the durable record).

Every outbound notification ends with a uniform footer:
    Sesión: <code>a3kp</code>

so the inbound webhook can parse the session ID back out of
`reply_to_message.text` regardless of which notification the asesor
hit "Reply" on.
"""
from __future__ import annotations

import logging
import os
import re

import httpx

log = logging.getLogger("holly.telegram")

# Mirrors the alphabet in static/js/chat.js / app.py (_SID_ALPHABET).
_SID_RE = re.compile(r"Sesi[oó]n:\s*([0-9a-z]{4})", re.IGNORECASE)


async def send_telegram(text: str, reply_to_message_id: int | None = None) -> int | None:
    """POST sendMessage. Returns the new message_id on success, else None."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log.warning("Telegram not configured; message dropped")
        return None
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: dict = {
        "chat_id": chat_id,
        "text": text[:4000],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = reply_to_message_id
        payload["allow_sending_without_reply"] = True
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(url, json=payload)
            if r.status_code != 200:
                log.warning("Telegram %s: %s", r.status_code, r.text[:200])
                return None
            return r.json().get("result", {}).get("message_id")
    except Exception as e:
        log.warning("Telegram send failed: %s", e)
        return None


def _h(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _footer(session_id: str) -> str:
    """Uniform last line used to make the session id reply-parseable."""
    return f"\nSesión: <code>{_h(session_id)}</code>"


async def notify_lead(lead: dict) -> None:
    body = (
        "<b>Nuevo lead — Holly Import</b>\n"
        f"Flujo: <b>{_h(lead.get('flow',''))}</b>\n"
        f"Marca: {_h(lead.get('brand',''))}\n"
        f"Modelo: {_h(lead.get('model_name','')) or '—'}\n"
        f"Nombre: {_h(lead.get('name',''))}\n"
        f"Teléfono: <code>{_h(lead.get('phone',''))}</code>\n"
        f"Preferencia: {_h(lead.get('contact_pref',''))}"
    )
    if lead.get("notes"):
        body += f"\nNotas: {_h(lead['notes'])}"
    body += _footer(lead.get("session_id", ""))
    await send_telegram(body)


async def notify_service(s: dict) -> None:
    body = (
        "<b>Nueva solicitud de servicio — Holly Import</b>\n"
        f"Nombre: {_h(s.get('name',''))}\n"
        f"Teléfono: <code>{_h(s.get('phone',''))}</code>\n"
        f"Vehículo: {_h(s.get('vehicle',''))}\n"
        f"Fecha preferida: {_h(s.get('preferred_date',''))} "
        f"{_h(s.get('preferred_time',''))}\n"
        f"Preferencia: {_h(s.get('contact_pref',''))}"
    )
    if s.get("notes"):
        body += f"\nNotas: {_h(s['notes'])}"
    body += _footer(s.get("session_id", ""))
    await send_telegram(body)


async def notify_chat_turn(session_id: str, user_msg: str, bot_reply: str,
                           context: str = "") -> None:
    body = (
        "<b>Chat — Holly Import</b>\n"
        f"Contexto: {_h(context) or '—'}\n"
        f"<b>Cliente:</b> {_h(user_msg)}\n"
        f"<b>Asesor:</b> {_h(bot_reply)}"
        f"{_footer(session_id)}"
    )
    await send_telegram(body)


def extract_session_id(text: str) -> str | None:
    """Pull the 4-char session id out of a quoted bot notification.

    Telegram strips the <code> tags on the way in, so the regex matches the
    plain "Sesión: a3kp" line every notification ends with.
    """
    if not text:
        return None
    m = _SID_RE.search(text)
    return m.group(1).lower() if m else None
