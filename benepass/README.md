# Benepass WFH stipend — monthly DoorDash receipt automation

Goal: before the end of each month, gather that month's DoorDash receipts from
Gmail, pick the best set against the **$300** stipend cap, render them to PDF,
and hand the packet to Julio so the final upload into the Benepass app takes
one tap.

A scheduled Routine fires a fresh Claude session near the end of each month
(cron `0 16 27 * *`) with instructions to follow this runbook. The repo is
cloned on `main` by default — fetch this branch first if the `benepass/`
directory is missing:

```
git fetch origin claude/benepass-stipend-automation-0aw5o9
git checkout claude/benepass-stipend-automation-0aw5o9
```

## Why the last step is manual

- Benepass has no email-in claims channel; claims are submitted in the
  Benepass app/web only, and this environment's network policy blocks
  `app.getbenepass.com` (proxy 403). Login also requires an OTP sent to the
  Benepass account email, which is not the connected Gmail.
- So the automation prepares everything and delivers it; Julio uploads the
  PDFs in the Benepass app under the WFH stipend and enters the amounts shown
  in the summary.

## Monthly procedure (for the Claude session the Routine spawns)

1. **Collect orders.** Gmail search (Gmail MCP):
   `from:doordash.com after:YYYY/MM/01 before:YYYY/MM/31` (current month).
   Relevant subjects:
   - `Order Confirmation for …` — every order; total is `Total: $X.XX`.
   - `Final receipt for …` — grocery/adjusted orders; **supersedes** the
     confirmation for the same order. Use `Final total charged`.
   - `Apologies for the issue with your order …` — support resolutions.
     If money was *refunded to the original payment method*, subtract it from
     that order's net. If it was *issued as DoorDash credits*, the card charge
     is unchanged — do not subtract, just note it.
   - Ignore login alerts, promos, sweepstakes.
2. **Extract.** `get_thread` results over ~25k tokens are saved to a file;
   parse the JSON with python, write each message's `htmlBody` unmodified to
   `receipts_html/<merchant>_<MMDD>.html`, and pull the totals.
3. **Select.** Build `orders.json`
   (`[{"id", "date", "merchant", "amount"}, ...]`) and run
   `python3 benepass/select_orders.py orders.json --cap 300`.
   Add `--allow-overflow` only if Julio has said he wants the cap fully
   consumed by a receipt that crosses it.
4. **Render.** `python3 benepass/render_pdf.py --dir receipts_html/ pdfs/`
   (headless Chromium; receipts are rendered exactly as received).
5. **Deliver.**
   - Send the PDFs + a summary table (date, merchant, amount, running total)
     to Julio with SendUserFile (status `proactive`).
   - Create a Gmail **draft** (never auto-send) to the connected Gmail
     address, subject `Benepass WFH stipend — <Month YYYY> receipts ($TOTAL)`,
     with the selected PDFs attached, so the packet is also reachable from
     the phone's Gmail app.
6. **Report.** Reply with the selection table, the unused remainder of the
   cap, and anything skipped (refunds, out-of-month orders).

Keep receipts and PDFs in the session scratchpad — never commit personal
receipt data to this repository.

## Files

- `render_pdf.py` — receipt HTML → PDF via headless Chromium.
- `select_orders.py` — subset choice maximizing claimed total under the cap.
