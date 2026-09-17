// Holly Import — analytics + lead attribution.
//
// Loaded in <head> before every other script. Three jobs:
//   1. Attribution: on every landing, read utm_* / gclid / fbclid / referrer and
//      keep FIRST-touch (never overwritten) and LAST-touch (updated whenever a
//      tagged link brings the visitor back) in localStorage, plus a random
//      visitor id. `window.hollyAttribution()` returns the flattened record.
//   2. Injection: wraps window.fetch so any POST to /api/lead or /api/service
//      carries `attribution` in its JSON body — main.js, chat.js and the
//      contact/parts forms need no changes. The backend stores it in the CSV
//      and puts "Origen" on the Telegram notification.
//   3. Events: forwards conversion events to GA4 (gtag) and Meta Pixel (fbq)
//      when those are configured (window.HOLLY_ANALYTICS from .env), and
//      always to window.dataLayer. Nothing here sends anything by itself when
//      neither ID is set — the site stays tracker-free until you opt in.
(() => {
  const LS_FIRST = "holly_attr_first", LS_LAST = "holly_attr_last", LS_VID = "holly_vid";
  const get = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
  const set = (k, v) => { try { localStorage.setItem(k, v); } catch {} };
  const getJSON = (k) => { try { return JSON.parse(get(k) || "null"); } catch { return null; } };
  const setJSON = (k, v) => set(k, JSON.stringify(v));

  // ---- 1. attribution ----
  const q = new URLSearchParams(location.search);
  const tagged = {};
  for (const k of ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"]) {
    const v = q.get(k); if (v) tagged[k.replace("utm_", "")] = v.slice(0, 120);
  }
  // Ads click ids imply a source when the URL has no utm_source.
  if (tagged.gclid && !tagged.source) { tagged.source = "google"; tagged.medium = tagged.medium || "cpc"; }
  if (tagged.fbclid && !tagged.source) { tagged.source = "facebook"; tagged.medium = tagged.medium || "paid_social"; }
  let ref = "";
  try { const r = document.referrer ? new URL(document.referrer) : null; if (r && r.host !== location.host) ref = r.host; } catch {}
  if (!tagged.source && ref) { tagged.source = ref.replace(/^www\./, ""); tagged.medium = "referral"; }
  const touch = { ...tagged, referrer: ref, landing: (location.pathname + location.search).slice(0, 200), ts: new Date().toISOString() };

  let vid = get(LS_VID);
  if (!vid) { vid = (crypto.randomUUID ? crypto.randomUUID().replace(/-/g, "").slice(0, 16) : Math.random().toString(36).slice(2, 18)); set(LS_VID, vid); }
  let first = getJSON(LS_FIRST);
  if (!first) { first = touch; setJSON(LS_FIRST, first); }
  // Last-touch only advances when this landing actually carries a source.
  if (touch.source || !getJSON(LS_LAST)) setJSON(LS_LAST, touch);
  const last = getJSON(LS_LAST) || touch;

  function attribution() {
    return {
      visitor_id: vid,
      first_source: first.source || "(direct)", first_medium: first.medium || "(none)",
      first_campaign: first.campaign || "", first_referrer: first.referrer || "", first_landing: first.landing || "",
      last_source: last.source || "(direct)", last_medium: last.medium || "(none)",
      last_campaign: last.campaign || "", last_content: last.content || "", last_term: last.term || "",
      gclid: last.gclid || first.gclid || "", fbclid: last.fbclid || first.fbclid || "",
      page: location.pathname.slice(0, 120),
    };
  }
  window.hollyAttribution = attribution;

  // ---- 3. events ----
  const META_MAP = { generate_lead: "Lead", service_booking: "Schedule", price_request_open: "InitiateCheckout",
                     open_chat: "Contact", whatsapp_click: "Contact", phone_click: "Contact", view_item: "ViewContent" };
  function track(name, params) {
    const p = Object.assign({}, params || {});
    try { if (typeof window.gtag === "function") window.gtag("event", name, p); } catch {}
    try {
      if (typeof window.fbq === "function") {
        if (META_MAP[name]) window.fbq("track", META_MAP[name], p); else window.fbq("trackCustom", name, p);
      }
    } catch {}
    (window.dataLayer = window.dataLayer || []).push(Object.assign({ event: name }, p));
  }
  window.hollyTrack = track;

  // Page-level events wait for the page to declare itself (window.HOLLY_PAGE is
  // set by the template at the end of <body>).
  document.addEventListener("DOMContentLoaded", () => {
    const pg = window.HOLLY_PAGE || {};
    if (pg.type === "model") track("view_item", { item_id: pg.id, item_name: pg.name, item_brand: pg.brand, item_category: pg.category });
    else if (pg.type) track("view_" + pg.type, {});
  });

  // Click-level events (capture phase so dialogs closing don't swallow them).
  document.addEventListener("click", (e) => {
    const t = e.target.closest("a, button");
    if (!t) return;
    const page = location.pathname;
    if (t.matches("[data-open-chat], #open-chat")) track("open_chat", { flow: t.dataset.chatFlow || "", model_id: t.dataset.chatModel || "", page });
    else if (t.matches("[data-ask-price]")) track("price_request_open", { model_id: t.dataset.askPrice || "", page });
    else if (t.matches('a[href*="wa.me"], a[href*="whatsapp.com"]')) track("whatsapp_click", { page });
    else if (t.matches('a[href^="tel:"]')) track("phone_click", { page });
    else if (t.matches(".chat__chips .chip")) track("chat_chip", { label: (t.textContent || "").trim().slice(0, 40), page });
  }, true);

  // ---- 2. inject attribution into lead / service POSTs + fire conversion events ----
  const nativeFetch = window.fetch;
  window.fetch = async function (input, init) {
    const url = typeof input === "string" ? input : (input && input.url) || "";
    const isLead = /\/api\/lead(?:\?|$)/.test(url), isSvc = /\/api\/service(?:\?|$)/.test(url);
    let payload = null;
    if ((isLead || isSvc) && init && typeof init.body === "string") {
      try { payload = JSON.parse(init.body); payload.attribution = attribution(); init = Object.assign({}, init, { body: JSON.stringify(payload) }); } catch {}
    }
    const res = await nativeFetch.call(this, input, init);
    if ((isLead || isSvc) && res && res.ok) {
      const a = attribution();
      track(isLead ? "generate_lead" : "service_booking",
            { flow: (payload && payload.flow) || (isSvc ? "servicio" : ""), brand: (payload && payload.brand) || "",
              model_id: (payload && payload.model_id) || "", source: a.last_source, medium: a.last_medium, campaign: a.last_campaign });
    }
    return res;
  };
})();
