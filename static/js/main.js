// Holly Import — main UI: filters, model detail dialog, ask-price dialog, mobile menu.

(() => {
  const BASE = window.HOLLY_BASE || "";

  // Year in footer
  const yr = document.getElementById("hf-year");
  if (yr) yr.textContent = new Date().getFullYear();

  // Mobile nav
  const menuBtn = document.getElementById("open-menu");
  const nav = document.querySelector(".hh__nav");
  if (menuBtn && nav) {
    menuBtn.addEventListener("click", () => nav.classList.toggle("is-open"));
  }

  // ----- model filters (Modelos page) -----
  const filterBar = document.getElementById("model-filters");
  const grid = document.getElementById("models-grid");
  if (filterBar && grid) {
    function applyFilter(f) {
      filterBar.querySelectorAll(".chip").forEach(c =>
        c.classList.toggle("is-active", c.dataset.filter === f)
      );
      grid.querySelectorAll(".card").forEach(card => {
        const brand = card.dataset.brand;
        const tags = (card.dataset.tags || "").split(",");
        const promo = card.dataset.promo === "yes";
        let show = true;
        if (f === "all") show = true;
        else if (f.startsWith("brand:")) show = brand === f.slice(6);
        else if (f.startsWith("tag:"))   show = tags.includes(f.slice(4));
        else if (f === "promo")          show = promo;
        card.classList.toggle("is-hidden", !show);
      });
    }
    filterBar.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (btn) applyFilter(btn.dataset.filter);
    });

    // honor ?marca= and ?promo= query params on first load
    const params = new URLSearchParams(location.search);
    const marca = params.get("marca");
    const promo = params.get("promo");
    if (marca === "MG" || marca === "Maxus") applyFilter(`brand:${marca}`);
    else if (promo) applyFilter("promo");
  }

  // ----- ask price dialog -----
  const priceDialog = document.getElementById("price-dialog");
  const priceForm   = document.getElementById("price-form");
  const priceStatus = document.getElementById("price-status");
  const priceModelId   = document.getElementById("price-model-id");
  const priceModelName = document.getElementById("price-model-name");

  document.addEventListener("click", (e) => {
    const ask = e.target.closest("[data-ask-price]");
    if (ask && priceDialog) {
      const id = ask.dataset.askPrice;
      const card = ask.closest(".card") || ask.closest("article");
      const name = card?.querySelector(".card__title")?.textContent?.trim() || "modelo";
      priceModelId.value = id;
      priceModelName.textContent = name;
      priceStatus.hidden = true;
      priceForm.reset();
      priceModelId.value = id; // restore after reset
      priceDialog.showModal();
    }
    const close = e.target.closest("[data-close-dialog]");
    if (close) close.closest("dialog")?.close();
  });

  priceForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(priceForm);
    const body = Object.fromEntries(fd.entries());
    body.flow = "compra";
    priceStatus.hidden = false;
    priceStatus.textContent = "Enviando…";
    priceStatus.className = "dialog__status";
    try {
      const r = await fetch(BASE + "/api/lead", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || "Error");
      priceStatus.textContent = "Gracias. Un asesor de Holly Import te contactará en breve.";
      priceStatus.classList.add("is-success");
      setTimeout(() => priceDialog.close(), 1800);
    } catch (err) {
      priceStatus.textContent = "No se pudo enviar. Intenta de nuevo.";
      priceStatus.classList.add("is-error");
    }
  });

  // ----- model detail dialog -----
  const modelDialog = document.getElementById("model-dialog");
  const modelDialogBody = document.getElementById("model-dialog-body");

  // Click anywhere on a card (but not on the inner buttons/links) navigates
  // to the per-model page.
  document.addEventListener("click", (e) => {
    const card = e.target.closest(".card[data-model-id]");
    if (!card) return;
    if (e.target.closest("button, a, dialog")) return;
    const id = card.dataset.modelId
      || card.querySelector("[data-ask-price]")?.dataset.askPrice;
    if (id) location.href = BASE + "/modelos/" + encodeURIComponent(id);
  });

  function renderModelDetail(m) {
    const specs = Object.entries(m.specs || {})
      .map(([k, v]) => `<li><strong>${escapeHtml(k)}</strong><span>${escapeHtml(String(v))}</span></li>`)
      .join("");
    const highlights = (m.highlights || [])
      .map(h => `<li>${escapeHtml(h)}</li>`)
      .join("");
    const promoBadge = m.promoEligible
      ? `<span class="mdl__promo" title="Asegúrate con 500">PROMO</span>` : "";
    const promoNote = m.promoEligible
      ? `<p class="card__tag" style="color:var(--c-crimson-2);font-weight:600">Aplica Asegúrate con 500</p>` : "";
    return `
      ${promoBadge}
      <div class="mdl">
        <div class="mdl__img">
          <img src="${BASE}/${escapeAttr(m.image)}" alt="${escapeAttr(m.name)}"
               onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'card__placeholder',textContent:'${escapeAttr(m.name)}'}))">
        </div>
        <div>
          <span class="card__brand">${escapeHtml(m.brand)}</span>
          <h3>${escapeHtml(m.name)}</h3>
          <p class="card__tag">${escapeHtml(m.tagline || "")}</p>
          ${promoNote}
          <ul class="mdl__specs">${specs}</ul>
          <h4 style="text-transform:none;letter-spacing:0;color:var(--c-white);font-family:Inter">Equipamiento destacado</h4>
          <ul class="mdl__highlights">${highlights}</ul>
          <div class="mdl__cta">
            <button class="btn btn--primary" type="button" data-ask-price="${escapeAttr(m.id)}" data-close-on-ask>Solicitar precio</button>
            <button class="btn btn--ghost" type="button" data-open-chat data-chat-model="${escapeAttr(m.id)}">Chat con Holly</button>
          </div>
        </div>
      </div>`;
  }

  function escapeHtml(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c])); }
  function escapeAttr(s) { return escapeHtml(s); }
})();
