#!/usr/bin/env python3
"""Pick the best subset of orders to submit against the monthly stipend cap.

Reads an orders JSON array on stdin (or a file path argument):
    [{"id": "aldi_0603", "date": "2026-06-03", "merchant": "ALDI", "amount": 213.05}, ...]

Prints the selection that maximizes the claimed total. By default the subset
must stay <= cap. With --allow-overflow, one extra receipt may push the total
past the cap (useful when the platform reimburses only up to the remaining
balance anyway), chosen to maximize cap utilization with the fewest receipts.

Usage: select_orders.py [orders.json] [--cap 300] [--allow-overflow]
"""
import itertools
import json
import sys


def best_subset(orders: list[dict], cap_cents: int) -> list[dict]:
    best: tuple[int, int, tuple] = (0, 0, ())  # (total, -count, ids)
    for r in range(1, len(orders) + 1):
        for combo in itertools.combinations(orders, r):
            total = sum(o["cents"] for o in combo)
            if total <= cap_cents:
                key = (total, -len(combo), tuple(o["id"] for o in combo))
                if key > best:
                    best = key
    ids = set(best[2])
    return [o for o in orders if o["id"] in ids]


def main(argv: list[str]) -> None:
    cap = 300.0
    allow_overflow = False
    path = None
    args = iter(argv)
    for a in args:
        if a == "--cap":
            cap = float(next(args))
        elif a == "--allow-overflow":
            allow_overflow = True
        else:
            path = a
    raw = open(path).read() if path else sys.stdin.read()
    orders = json.loads(raw)
    for o in orders:
        o["cents"] = round(o["amount"] * 100)
    cap_cents = round(cap * 100)

    pick = best_subset(orders, cap_cents)
    total = sum(o["cents"] for o in pick)
    if allow_overflow and total < cap_cents:
        # top up with the smallest receipt that crosses the cap
        rest = sorted((o for o in orders if o not in pick), key=lambda o: o["cents"])
        for o in rest:
            if total + o["cents"] >= cap_cents:
                pick.append(o)
                total += o["cents"]
                break

    for o in pick:
        print(f"  {o['date']}  {o['merchant']:<20} ${o['cents'] / 100:.2f}")
    print(f"selected {len(pick)} receipts, total ${total / 100:.2f} against cap ${cap:.2f}")
    print(json.dumps([o["id"] for o in pick]))


if __name__ == "__main__":
    main(sys.argv[1:])
