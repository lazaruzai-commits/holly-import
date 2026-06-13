"""Anchor & Oar — boat rental site with a built-in MCP server.

One process serves three things off the same booking store:
  * a website to browse the fleet and book a boat   (/, /boats/{id})
  * a JSON REST API                                  (/api/*)
  * an MCP server over Streamable HTTP               (/mcp)

Run locally:
    cd boat-rental
    pip install -r requirements.txt
    uvicorn app:app --reload --port 8000

Then open http://localhost:8000 in a browser, or point an MCP client at
http://localhost:8000/mcp to rent a boat from an AI agent.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

import store
from mcp_server import mcp

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("boat-rental")

PROJECT_ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))

# The MCP Streamable HTTP transport runs a session manager that must be
# started/stopped with the app. Mounting a sub-app does not run its
# lifespan automatically, so we drive it from the parent app's lifespan.
mcp_app = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        log.info("MCP server mounted at /mcp")
        yield


app = FastAPI(title="Anchor & Oar — Boat Rentals", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")
# The MCP endpoint. Clients connect to <host>/mcp/ (Streamable HTTP).
app.mount("/mcp", mcp_app)


# ---------- website ----------

@app.get("/", response_class=HTMLResponse)
async def page_home(request: Request):
    return templates.TemplateResponse(
        request, "index.html", {"request": request, "boats": store.list_boats()}
    )


@app.get("/boats/{boat_id}", response_class=HTMLResponse)
async def page_boat(request: Request, boat_id: str):
    boat = store.get_boat(boat_id)
    if not boat:
        raise HTTPException(404, "Boat not found")
    return templates.TemplateResponse(
        request, "boat.html", {"request": request, "boat": boat}
    )


# ---------- REST API ----------

@app.get("/api/boats")
async def api_boats(
    location: str | None = None,
    type: str | None = None,
    min_capacity: int | None = None,
    max_price_per_day: float | None = None,
):
    return {
        "boats": store.list_boats(
            location=location,
            boat_type=type,
            min_capacity=min_capacity,
            max_price_per_day=max_price_per_day,
        )
    }


@app.get("/api/boats/{boat_id}")
async def api_boat(boat_id: str):
    boat = store.get_boat(boat_id)
    if not boat:
        raise HTTPException(404, "Boat not found")
    return boat


@app.get("/api/quote")
async def api_quote(boat_id: str, start_date: str, end_date: str):
    try:
        return store.quote(boat_id, start_date, end_date)
    except store.BookingError as e:
        raise HTTPException(400, str(e))


class BookingRequest(BaseModel):
    boat_id: str = Field(min_length=1)
    customer_name: str = Field(min_length=2, max_length=120)
    start_date: str = Field(min_length=10, max_length=10)
    end_date: str = Field(min_length=10, max_length=10)
    customer_email: str = Field(default="", max_length=200)
    party_size: int | None = Field(default=None, ge=1, le=100)
    notes: str = Field(default="", max_length=1000)


@app.post("/api/bookings")
async def api_create_booking(req: BookingRequest):
    try:
        booking = store.create_booking(
            boat_id=req.boat_id,
            customer_name=req.customer_name,
            start_date=req.start_date,
            end_date=req.end_date,
            customer_email=req.customer_email,
            party_size=req.party_size,
            notes=req.notes,
        )
    except store.BookingError as e:
        raise HTTPException(400, str(e))
    return booking


@app.get("/api/bookings/{booking_id}")
async def api_get_booking(booking_id: str):
    booking = store.get_booking(booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")
    return booking


@app.post("/api/bookings/{booking_id}/cancel")
async def api_cancel_booking(booking_id: str):
    try:
        return store.cancel_booking(booking_id)
    except store.BookingError as e:
        raise HTTPException(400, str(e))


@app.get("/api/health")
async def api_health():
    return {"ok": True, "boats": len(store.list_boats()), "mcp": "/mcp"}
