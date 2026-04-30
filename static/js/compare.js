// Holly Import — Compare page logic.

(() => {
  const BASE = window.HOLLY_BASE || "";
  const sel  = document.getElementById("cmp-holly");
  const rivalSel = document.getElementById("cmp-rival");
  const out  = document.getElementById("cmp-out");
  if (!sel || !rivalSel || !out) return;

  let MODELS = [];
  let COMPETITOR_LABELS = {}; // populated lazily

  async function loadModels() {
    const r = await fetch(BASE + "/api/models");
    const j = await r.json();
    MODELS = j.models || [];
  }

  sel.addEventListener("change", async () => {
    out.innerHTML = "";
    rivalSel.innerHTML = "";
    rivalSel.disabled = true;
    const id = sel.value;
    if (!id) return;
    if (!MODELS.length) await loadModels();
    const m = MODELS.find(x => x.id === id);
    if (!m) return;
    rivalSel.disabled = false;
    rivalSel.innerHTML = `<option value="">— elegir competidor —</option>`;
    // We need labels; fetch model detail (which includes hydrated competitors)
    try {
      const r = await fetch(BASE + "/api/models/" + encodeURIComponent(id));
      const j = await r.json();
      (j.competitors || []).forEach(c => {
        COMPETITOR_LABELS[c.id] = `${c.brand} ${c.model}`;
        const opt = document.createElement("option");
        opt.value = c.id;
        opt.textContent = `${c.brand} ${c.model}`;
        rivalSel.appendChild(opt);
      });
    } catch {
      out.innerHTML = `<p>No se pudieron cargar los competidores.</p>`;
    }
  });

  rivalSel.addEventListener("change", async () => {
    if (!sel.value || !rivalSel.value) { out.innerHTML = ""; return; }
    out.innerHTML = `<p>Cargando comparativa…</p>`;
    try {
      const r = await fetch(BASE + "/api/compare?holly=" + encodeURIComponent(sel.value)
                          + "&competitor=" + encodeURIComponent(rivalSel.value));
      const j = await r.json();
      out.innerHTML = renderCompare(j.holly, j.competitor);
    } catch {
      out.innerHTML = `<p>No se pudo cargar la comparativa.</p>`;
    }
  });

  function renderCompare(h, c) {
    const hSpecs = renderSpecs(h.specs);
    const cSpecs = renderSpecs({
      motor: c.motor, potencia: c.potencia, torque: c.torque,
      transmision: c.transmision, asientos: c.asientos,
    });
    const v = c.vsHolly || {};
    const badgeMap = {
      "mejor-valor":   "Mejor valor",
      "mas-equipado":  "Más equipado",
      "mas-potencia":  "Mayor potencia",
      "mas-economico": "Más económico",
    };
    const badgeLabel = badgeMap[v.relativeBadge] || "Ventaja Holly";
    const points = (v.puntos || []).map(p => `<li>${esc(p)}</li>`).join("");

    return `
      <div class="cmp">
        <div class="cmp__col cmp__col--holly">
          <span class="cmp__badge cmp__badge--${esc(v.relativeBadge || "mejor-valor")}">${esc(badgeLabel)}</span>
          <span class="card__brand">${esc(h.brand)}</span>
          <h3>${esc(h.name)}</h3>
          <p class="card__tag">${esc(h.tagline || "")}</p>
          <ul class="cmp__specs">${hSpecs}</ul>
        </div>
        <div class="cmp__col">
          <span class="card__brand">${esc(c.brand)}</span>
          <h3>${esc(c.model)}</h3>
          <ul class="cmp__specs">${cSpecs}</ul>
        </div>
        <div class="cmp__sum">
          <h4>Por qué elegir Holly Import</h4>
          <p>${esc(v.summary || "")}</p>
          <ul>${points}</ul>
        </div>
      </div>
    `;
  }

  function renderSpecs(s) {
    return Object.entries(s || {})
      .filter(([_, v]) => v != null && v !== "")
      .map(([k, v]) => `<li><strong>${esc(k)}</strong><span>${esc(String(v))}</span></li>`)
      .join("");
  }

  function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c])); }

  loadModels();
})();
