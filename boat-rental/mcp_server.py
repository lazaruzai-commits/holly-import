"""MCP server for the boat-rental site.

Exposes the booking workflow as MCP tools so any MCP client (Claude
Desktop, Claude Code, the Agents SDK, etc.) can browse the fleet and rent a
boat through natural language. Every tool wraps the shared `store` module,
so MCP bookings and website bookings share one source of truth.

Served over the Streamable HTTP transport, mounted by `app.py` at `/mcp`.
"""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

import store

# stateless_http=True: each tool call is an independent HTTP request with no
# server-side session to keep alive. Simpler to mount inside the FastAPI app
# and friendlier to load balancers; we hold no per-connection state anyway.
mcp = FastMCP(
    "boat-rental",
    instructions=(
        "Tools for browsing and renting boats from the Anchor & Oar fleet. "
        "Typical flow: call list_boats (optionally filtered) to find a boat, "
        "get_quote to price specific dates and confirm availability, then "
        "book_boat to reserve it. Always confirm the dates, total price, and "
        "the customer's name with the user before calling book_boat. Use "
        "get_booking to look up an existing reservation and cancel_booking to "
        "release one. Dates are YYYY-MM-DD."
    ),
    stateless_http=True,
)


@mcp.tool()
def list_boats(
    location: str | None = None,
    boat_type: str | None = None,
    min_capacity: int | None = None,
    max_price_per_day: float | None = None,
) -> list[dict[str, Any]]:
    """List boats available to rent, with optional filters.

    Args:
        location: Case-insensitive substring of the boat's home port
            (e.g. "Miami", "CA").
        boat_type: Case-insensitive substring of the category
            (e.g. "Sailboat", "Pontoon", "Yacht").
        min_capacity: Only boats that seat at least this many guests.
        max_price_per_day: Only boats at or under this daily rate (USD).

    Returns the full spec for each matching boat, including its `id` (needed
    for get_quote and book_boat), daily price, capacity, and amenities.
    """
    return store.list_boats(
        location=location,
        boat_type=boat_type,
        min_capacity=min_capacity,
        max_price_per_day=max_price_per_day,
    )


@mcp.tool()
def get_boat(boat_id: str) -> dict[str, Any]:
    """Get the full details of a single boat by its id."""
    boat = store.get_boat(boat_id)
    if not boat:
        raise ValueError(f"No boat with id {boat_id!r}. Call list_boats to see ids.")
    return boat


@mcp.tool()
def get_quote(boat_id: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Price a charter for specific dates and report whether it's available.

    Args:
        boat_id: The boat's id (from list_boats).
        start_date: First day of the charter, YYYY-MM-DD.
        end_date: Last day of the charter, YYYY-MM-DD (inclusive).

    Returns the day count, per-day rate, total price, and an `available`
    flag. Does not reserve anything — call book_boat to confirm.
    """
    try:
        return store.quote(boat_id, start_date, end_date)
    except store.BookingError as e:
        raise ValueError(str(e))


@mcp.tool()
def book_boat(
    boat_id: str,
    customer_name: str,
    start_date: str,
    end_date: str,
    customer_email: str = "",
    party_size: int | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Reserve a boat for the given dates and return the confirmed booking.

    Confirm the boat, dates, total price, and customer name with the user
    before calling this. Fails with a clear message if the boat is unknown,
    the dates are invalid, the party exceeds capacity, or the dates conflict
    with an existing booking.

    Args:
        boat_id: The boat's id (from list_boats).
        customer_name: Name the reservation is held under.
        start_date: First day of the charter, YYYY-MM-DD.
        end_date: Last day of the charter, YYYY-MM-DD (inclusive).
        customer_email: Optional contact email for the confirmation.
        party_size: Optional number of guests; validated against capacity.
        notes: Optional free-text request (occasion, add-ons, etc.).

    Returns the booking record, including its `id` and `total_price`.
    """
    try:
        return store.create_booking(
            boat_id=boat_id,
            customer_name=customer_name,
            start_date=start_date,
            end_date=end_date,
            customer_email=customer_email,
            party_size=party_size,
            notes=notes,
        )
    except store.BookingError as e:
        raise ValueError(str(e))


@mcp.tool()
def get_booking(booking_id: str) -> dict[str, Any]:
    """Look up an existing booking by its id (e.g. "bk-7h2k9p")."""
    booking = store.get_booking(booking_id)
    if not booking:
        raise ValueError(f"No booking with id {booking_id!r}.")
    return booking


@mcp.tool()
def cancel_booking(booking_id: str) -> dict[str, Any]:
    """Cancel a booking by its id, freeing the dates for others to book."""
    try:
        return store.cancel_booking(booking_id)
    except store.BookingError as e:
        raise ValueError(str(e))
