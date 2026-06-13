"""Shared catalog + booking store for the boat-rental site.

Both the website's REST API and the MCP server call into this module, so a
boat booked by an AI agent over MCP and a boat booked through the web form
land in the same place and conflict-check against each other.

Catalog is read-only JSON. Bookings persist to a JSON file (gitignored) so
they survive a restart without pulling in a database dependency.
"""
from __future__ import annotations

import json
import secrets
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent / "data"
BOATS_FILE = DATA_DIR / "boats.json"
BOOKINGS_FILE = DATA_DIR / "bookings.json"

# A booking id is short and easy to read back over a phone or chat.
# i/l/o/0/1 omitted to avoid ambiguity.
_ID_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"

# Guards the bookings file against interleaved read/modify/write from
# concurrent requests (web + MCP can both write).
_LOCK = threading.Lock()


class BookingError(Exception):
    """Raised for any caller-correctable problem (unknown boat, bad dates,
    date conflict). Carries a plain-language message safe to show a user."""


# ---------- catalog ----------

def _load_boats() -> list[dict[str, Any]]:
    return json.loads(BOATS_FILE.read_text(encoding="utf-8"))["boats"]


_BOATS = _load_boats()
_BOATS_BY_ID = {b["id"]: b for b in _BOATS}


def list_boats(
    *,
    location: str | None = None,
    boat_type: str | None = None,
    min_capacity: int | None = None,
    max_price_per_day: float | None = None,
) -> list[dict[str, Any]]:
    """Return catalog boats, optionally narrowed by simple filters.

    Filters are case-insensitive substring matches for text fields. Any
    filter left as None is ignored.
    """
    out = []
    for b in _BOATS:
        if location and location.lower() not in b["location"].lower():
            continue
        if boat_type and boat_type.lower() not in b["type"].lower():
            continue
        if min_capacity is not None and b["capacity"] < min_capacity:
            continue
        if max_price_per_day is not None and b["price_per_day"] > max_price_per_day:
            continue
        out.append(b)
    return out


def get_boat(boat_id: str) -> dict[str, Any] | None:
    return _BOATS_BY_ID.get(boat_id)


# ---------- bookings persistence ----------

def _read_bookings() -> list[dict[str, Any]]:
    if not BOOKINGS_FILE.is_file():
        return []
    return json.loads(BOOKINGS_FILE.read_text(encoding="utf-8"))


def _write_bookings(rows: list[dict[str, Any]]) -> None:
    BOOKINGS_FILE.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _new_booking_id() -> str:
    return "bk-" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(6))


# ---------- date helpers ----------

def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise BookingError(
            f"{field} must be a date in YYYY-MM-DD format (got {value!r})."
        )


def _ranges_overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    # Bookings are inclusive of start and end day; a boat returned on the
    # same day it's re-chartered would need turnaround, so treat touching
    # ranges as a conflict.
    return a_start <= b_end and b_start <= a_end


# ---------- availability + booking ----------

def is_available(boat_id: str, start: str, end: str) -> bool:
    """True if `boat_id` has no active booking overlapping [start, end]."""
    s = _parse_date(start, "start_date")
    e = _parse_date(end, "end_date")
    if e < s:
        raise BookingError("end_date cannot be before start_date.")
    for row in _read_bookings():
        if row["boat_id"] != boat_id or row["status"] == "cancelled":
            continue
        if _ranges_overlap(
            s, e, _parse_date(row["start_date"], "start_date"),
            _parse_date(row["end_date"], "end_date"),
        ):
            return False
    return True


def quote(boat_id: str, start: str, end: str) -> dict[str, Any]:
    """Price a hypothetical charter without booking it."""
    boat = get_boat(boat_id)
    if not boat:
        raise BookingError(f"No boat with id {boat_id!r}. Use list_boats to see ids.")
    s = _parse_date(start, "start_date")
    e = _parse_date(end, "end_date")
    if e < s:
        raise BookingError("end_date cannot be before start_date.")
    days = (e - s).days + 1  # inclusive
    subtotal = boat["price_per_day"] * days
    return {
        "boat_id": boat_id,
        "boat_name": boat["name"],
        "start_date": start,
        "end_date": end,
        "days": days,
        "price_per_day": boat["price_per_day"],
        "total_price": subtotal,
        "currency": "USD",
        "available": is_available(boat_id, start, end),
    }


def create_booking(
    *,
    boat_id: str,
    customer_name: str,
    start_date: str,
    end_date: str,
    customer_email: str = "",
    party_size: int | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Reserve a boat. Raises BookingError on any validation/conflict issue.

    Holds the lock across the conflict check + write so two simultaneous
    requests can't both grab the same dates.
    """
    boat = get_boat(boat_id)
    if not boat:
        raise BookingError(f"No boat with id {boat_id!r}. Use list_boats to see ids.")
    if not customer_name or not customer_name.strip():
        raise BookingError("customer_name is required.")
    if party_size is not None and party_size > boat["capacity"]:
        raise BookingError(
            f"{boat['name']} holds {boat['capacity']} guests, "
            f"but party_size is {party_size}."
        )

    s = _parse_date(start_date, "start_date")
    e = _parse_date(end_date, "end_date")
    if e < s:
        raise BookingError("end_date cannot be before start_date.")
    days = (e - s).days + 1

    with _LOCK:
        rows = _read_bookings()
        for row in rows:
            if row["boat_id"] != boat_id or row["status"] == "cancelled":
                continue
            if _ranges_overlap(
                s, e, _parse_date(row["start_date"], "start_date"),
                _parse_date(row["end_date"], "end_date"),
            ):
                raise BookingError(
                    f"{boat['name']} is already booked between "
                    f"{row['start_date']} and {row['end_date']}. "
                    "Pick different dates or another boat."
                )
        booking = {
            "id": _new_booking_id(),
            "boat_id": boat_id,
            "boat_name": boat["name"],
            "customer_name": customer_name.strip(),
            "customer_email": customer_email.strip(),
            "party_size": party_size,
            "start_date": start_date,
            "end_date": end_date,
            "days": days,
            "price_per_day": boat["price_per_day"],
            "total_price": boat["price_per_day"] * days,
            "currency": "USD",
            "status": "confirmed",
            "notes": notes.strip(),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        rows.append(booking)
        _write_bookings(rows)
    return booking


def get_booking(booking_id: str) -> dict[str, Any] | None:
    for row in _read_bookings():
        if row["id"] == booking_id:
            return row
    return None


def cancel_booking(booking_id: str) -> dict[str, Any]:
    with _LOCK:
        rows = _read_bookings()
        for row in rows:
            if row["id"] == booking_id:
                if row["status"] == "cancelled":
                    raise BookingError(f"Booking {booking_id} is already cancelled.")
                row["status"] = "cancelled"
                _write_bookings(rows)
                return row
    raise BookingError(f"No booking with id {booking_id!r}.")
