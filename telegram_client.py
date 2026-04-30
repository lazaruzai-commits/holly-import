"""Telegram Bot API forwarder.

Used to push every captured lead, service booking, and free-text chat turn
to https://t.me/HollyImportBot so a human can follow up. Failures are
non-fatal — we log and continue (the CSV is the durable record).
"""
from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("holly.telegram")


async def send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log.warning("Telegram not configured; message dropped")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text[:4000],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(url, json=payload)
            if r.status_code != 200:
                log.warning("Telegram %s: %s", r.status_code, r.text[:200])
                return False
            return True
    except Exception as e:
        log.warning("Telegram send failed: %s", e)
        return False


def _h(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def notify_lead(lead: dict) -> None:
    body = (
        "<b>Nuevo lead — Holly Import</b>\n"
        f"Flujo: <b>{_h(lead.get('flow',''))}</b>\n"
        f"Marca: {_h(lead.get('brand',''))}\n"
        f"Modelo: {_h(lead.get('model_name','')) or '—'}\n"
        f"Nombre: {_h(lead.get('name',''))}\n"
        f"Teléfono: <code>{_h(lead.get('phone',''))}</code>\n"
        f"Preferencia: {_h(lead.get('contact_pref',''))}\n"
        f"Sesión: <code>{_h(lead.get('session_id',''))}</code>"
    )
    if lead.get("notes"):
        body += f"\nNotas: {_h(lead['notes'])}"
    await send_telegram(body)


async def notify_service(s: dict) -> None:
    body = (
        "<b>Nueva solicitud de servicio — Holly Import</b>\n"
        f"Nombre: {_h(s.get('name',''))}\n"
        f"Teléfono: <code>{_h(s.get('phone',''))}</code>\n"
        f"Vehículo: {_h(s.get('vehicle',''))}\n"
        f"Fecha preferida: {_h(s.get('preferred_date',''))} "
        f"{_h(s.get('preferred_time',''))}\n"
        f"Preferencia: {_h(s.get('contact_pref',''))}\n"
        f"Sesión: <code>{_h(s.get('session_id',''))}</code>"
    )
    if s.get("notes"):
        body += f"\nNotas: {_h(s['notes'])}"
    await send_telegram(body)


async def notify_chat_turn(session_id: str, user_msg: str, bot_reply: str,
                           context: str = "") -> None:
    body = (
        f"<b>Chat — Holly Import</b> <code>{_h(session_id)}</code>\n"
        f"Contexto: {_h(context) or '—'}\n"
        f"<b>Cliente:</b> {_h(user_msg)}\n"
        f"<b>Asesor:</b> {_h(bot_reply)}"
    )
    await send_telegram(body)
