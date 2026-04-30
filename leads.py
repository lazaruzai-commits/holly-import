"""CSV persistence for leads, service bookings, and chat transcripts.

Each writer is append-only and writes a header row the first time the file
is created. Files live under ./leads/ which is gitignored so customer data
never lands in source control.
"""
from __future__ import annotations

import csv
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEADS_DIR = Path(__file__).parent / "leads"
LEADS_DIR.mkdir(exist_ok=True)

_LOCK = threading.Lock()


def _append(path: Path, row: dict[str, Any], fieldnames: list[str]) -> None:
    new_file = not path.exists()
    with _LOCK, path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


LEAD_FIELDS = [
    "ts", "session_id", "flow", "brand", "model_id", "model_name",
    "name", "phone", "contact_pref", "notes",
]


def save_lead(*, session_id: str, brand: str = "", model_id: str = "",
              model_name: str = "", name: str = "", phone: str = "",
              contact_pref: str = "call_text", notes: str = "",
              flow: str = "compra") -> dict[str, Any]:
    row = {
        "ts": _now(),
        "session_id": session_id,
        "flow": flow,
        "brand": brand,
        "model_id": model_id,
        "model_name": model_name,
        "name": name,
        "phone": phone,
        "contact_pref": contact_pref,
        "notes": notes,
    }
    _append(LEADS_DIR / "leads.csv", row, LEAD_FIELDS)
    return row


SERVICE_FIELDS = [
    "ts", "session_id", "name", "phone", "contact_pref",
    "vehicle", "preferred_date", "preferred_time", "notes",
]


def save_service(*, session_id: str, name: str = "", phone: str = "",
                 contact_pref: str = "call_text", vehicle: str = "",
                 preferred_date: str = "", preferred_time: str = "",
                 notes: str = "") -> dict[str, Any]:
    row = {
        "ts": _now(),
        "session_id": session_id,
        "name": name,
        "phone": phone,
        "contact_pref": contact_pref,
        "vehicle": vehicle,
        "preferred_date": preferred_date,
        "preferred_time": preferred_time,
        "notes": notes,
    }
    _append(LEADS_DIR / "services.csv", row, SERVICE_FIELDS)
    return row


CHAT_FIELDS = ["ts", "session_id", "role", "content", "context"]


def save_chat_message(*, session_id: str, role: str, content: str,
                      context: str = "") -> None:
    row = {
        "ts": _now(),
        "session_id": session_id,
        "role": role,
        "content": content,
        "context": context,
    }
    _append(LEADS_DIR / "chat_log.csv", row, CHAT_FIELDS)
