// Simulador de cuotas (/simulador).
// Everything is computed here, in the browser, from data/financing.json
// (rendered into #sim's data-plans). Formula per plan:
//   financed = price * (1 + surcharge_pct/100) - inicial
//   cuota    = financed / months            (equal monthly instalments)
//   total    = inicial + cuota * months
// Dates are indicative: inicial today, cuota k one month apart.
(() => {
  const root = document.getElementById("sim");
  if (!root) return;
  const PLANS = JSON.parse(root.dataset.plans || "[]");
  const INICIAL_DEFAULT = Number(root.dataset.inicialDefault || 0);
  const WA = (root.dataset.whatsapp || "").replace(/\D/g, "");

  const $ = (id) => document.getElementById(id);
  const form = $("sim-form"), modelSel = $("sim-model"), priceIn = $("sim-price"), inicialIn = $("sim-inicial");
  const out = $("sim-out"), empty = $("sim-empty"), rows = $("sim-rows"), err = $("sim-error");
  const ask = $("sim-ask"), wa = $("sim-wa"), copyBtn = $("sim-copy");

  const fmt = new Intl.NumberFormat("es-VE", { style: "currency", currency: "USD", currencyDisplay: "narrowSymbol", maximumFractionDigits: 2, minimumFractionDigits: 2 });
  const money = (n) => fmt.format(n);
  const dateFmt = new Intl.DateTimeFormat("es-VE", { day: "2-digit", month: "short", year: "numeric" });
  function addMonths(d, k) { const x = new Date(d); x.setMonth(x.getMonth() + k); return x; }

  let last = null;   // last computed plan, for the CTA / WhatsApp / copy
  let trackTimer = null;

  function selectedPlan() {
    const id = form.elements.plan.value;
    return PLANS.find(p => p.id === id) || PLANS[0];
  }
  function modelInfo() {
    const o = modelSel.selectedOptions[0];
    return o && o.value ? { id: o.value, name: o.dataset.name, brand: o.dataset.brand, price: o.dataset.price ? Number(o.dataset.price) : null } : null;
  }

  function compute() {
    const plan = selectedPlan();
    const price = Number(priceIn.value);
    const inicial = Number(inicialIn.value);
    const minInicial = Number(plan.inicial ?? INICIAL_DEFAULT);
    err.hidden = true;
    if (!price || price < 1000) { out.hidden = true; empty.hidden = false; last = null; return; }
    if (inicial < minInicial) { err.textContent = `La inicial mínima de este plan es ${money(minInicial)}.`; err.hidden = false; }
    if (inicial >= price) { err.textContent = "La inicial no puede ser igual o mayor al precio."; err.hidden = false; out.hidden = true; empty.hidden = false; last = null; return; }

    const surcharge = Number(plan.surcharge_pct || 0) / 100;
    const financed = price * (1 + surcharge) - inicial;
    const cuota = financed / plan.months;
    const total = inicial + cuota * plan.months;
    const today = new Date();

    const list = [{ label: "Inicial · a la firma", date: today, amount: inicial }];
    for (let k = 1; k <= plan.months; k++) list.push({ label: `Cuota ${k}`, date: addMonths(today, k), amount: cuota });

    rows.innerHTML = list.map((r, i) => `<tr${i === 0 ? ' class="is-inicial"' : ""}><td>${r.label}</td><td>${dateFmt.format(r.date)}</td><td class="num">${money(r.amount)}</td></tr>`).join("");
    $("k-cuota").textContent = money(cuota);
    $("k-inicial").textContent = money(inicial);
    $("k-plazo").textContent = `${plan.months} meses`;
    $("k-total").textContent = money(total);
    $("sim-total-row").textContent = money(total);
    empty.hidden = true; out.hidden = false;

    const m = modelInfo();
    last = { plan, price, inicial, cuota, total, model: m, lines: list };
    const label = m ? m.name : "el vehículo";
    const note = `Plan ${plan.name} (${plan.months} cuotas): precio ${money(price)}, inicial ${money(inicial)}, cuota mensual ${money(cuota)}, total ${money(total)}.`;
    ask.dataset.askPrice = m ? m.id : "";
    ask.dataset.askName = label;
    ask.dataset.askNotes = `Simulador de cuotas — ${label}. ${note}`;
    if (WA) {
      const text = `Hola Holly Import, me interesa ${label} con ${PLANS.length ? "Engánchate con 500" : "financiamiento"}. ${note}`;
      wa.href = `https://wa.me/${WA}?text=${encodeURIComponent(text)}`; wa.hidden = false;
    }
    // One analytics event per settled result, not one per keystroke.
    clearTimeout(trackTimer);
    trackTimer = setTimeout(() => { if (window.hollyTrack) window.hollyTrack("view_simulador_result", { model_id: m ? m.id : "", brand: m ? m.brand : "", flow: `plan_${plan.id}` }); }, 900);
  }

  // Preselected model with a known price fills the price box.
  function syncModel() {
    const m = modelInfo();
    const hint = $("sim-price-hint");
    if (m && m.price) { priceIn.value = m.price; hint.textContent = `Precio referencial de ${m.name}. Puedes ajustarlo.`; }
    else hint.textContent = "Indica el precio que te dio tu asesor o el que tienes en mente.";
    compute();
  }
  modelSel.addEventListener("change", syncModel);
  form.addEventListener("input", (e) => { if (e.target !== modelSel) compute(); });
  form.addEventListener("submit", (e) => { e.preventDefault(); compute(); });

  copyBtn.addEventListener("click", async () => {
    if (!last) return;
    const text = [`Holly Import — Simulador de cuotas`, last.model ? last.model.name : "", `Plan ${last.plan.name}`,
      ...last.lines.map(r => `${r.label}\t${dateFmt.format(r.date)}\t${money(r.amount)}`), `Total\t\t${money(last.total)}`].filter(Boolean).join("\n");
    try { await navigator.clipboard.writeText(text); copyBtn.textContent = "Copiado"; }
    catch (e) { copyBtn.textContent = "No se pudo copiar"; }
    setTimeout(() => (copyBtn.textContent = "Copiar tabla"), 1500);
  });

  syncModel();
  if (modelSel.value) priceIn.focus();
})();
