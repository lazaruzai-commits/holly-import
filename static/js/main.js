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
    filterBar.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      filterBar.querySelectorAll(".chip").forEach(c => c.classList.remove("is-active"));
      btn.classList.add("is-active");
      const f = btn.dataset.filter;
      grid.querySelectorAll(".card").forEach(card => {
        const brand = card.dataset.brand;
        const cat = card.dataset.category;
        const promo = card.dataset.promo === "yes";
        const show =
          f === "all" ? true :
          f === "MG" || f === "Maxus" ? brand === f :
          f === "passenger" || f === "commercial" ? cat === f :
          f === "promo" ? promo : true;
        card.classList.toggle("is-hidden", !show);
      });
    });

    // honor ?marca= and ?promo= query params on first load
    const params = new URLSearchParams(location.search);
    const marca = params.get("marca");
    const promo = params.get("promo");
    if (marca === "MG" || marca === "Maxus") {
      filterBar.querySelector(`[data-filter="${marca}"]`)?.click();
    } else if (promo) {
      filterBar.querySelector(`[data-filter="promo"]`)?.click();
    }
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

  document.addEventListener("click", async (e) => {
    const trigger = e.target.closest("[data-model-detail]");
    if (!trigger || !modelDialog) return;
    const id = trigger.dataset.modelDetail;
    modelDialogBody.innerHTML = `<div class="mdl"><p>Cargando…</p></div>`;
    modelDialog.showModal();
    try {
      const r = await fetch(BASE + "/api/models/" + encodeURIComponent(id));
      const j = await r.json();
      const m = j.model;
      modelDialogBody.innerHTML = renderModelDetail(m);
    } catch (err) {
      modelDialogBody.innerHTML = `<div class="mdl"><p>No se pudo cargar el modelo.</p></div>`;
    }
  });

  function renderModelDetail(m) {
    const specs = Object.entries(m.specs || {})
      .map(([k, v]) => `<li><strong>${escapeHtml(k)}</strong><span>${escapeHtml(String(v))}</span></li>`)
      .join("");
    const highlights = (m.highlights || [])
      .map(h => `<li>${escapeHtml(h)}</li>`)
      .join("");
    const promoTag = m.promoEligible
      ? `<span class="card__badge" style="position:static;display:inline-block;margin-bottom:.5rem">Asegúrate con 500</span>` : "";
    return `
      <div class="mdl">
        <div class="mdl__img">
          <img src="${BASE}/${escapeAttr(m.image)}" alt="${escapeAttr(m.name)}"
               onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'card__placeholder',textContent:'${escapeAttr(m.name)}'}))">
        </div>
        <div>
          <span class="card__brand">${escapeHtml(m.brand)}</span>
          <h3>${escapeHtml(m.name)}</h3>
          <p class="card__tag">${escapeHtml(m.tagline || "")}</p>
          ${promoTag}
          <ul class="mdl__specs">${specs}</ul>
          <h4 style="text-transform:none;letter-spacing:0;color:var(--c-white);font-family:Inter">Equipamiento destacado</h4>
          <ul class="mdl__highlights">${highlights}</ul>
          <div class="mdl__cta">
            <button class="btn btn--primary" type="button" data-ask-price="${escapeAttr(m.id)}" data-close-on-ask>Solicitar precio</button>
            <button class="btn btn--ghost" type="button" data-open-chat data-chat-model="${escapeAttr(m.id)}">Hablar con asesor</button>
          </div>
        </div>
      </div>`;
  }

  function escapeHtml(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c])); }
  function escapeAttr(s) { return escapeHtml(s); }
})();
