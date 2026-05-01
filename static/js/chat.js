// Holly Import — side-modal chat with Compra / Servicios flows + free text via OpenRouter.

(() => {
  const BASE = window.HOLLY_BASE || "";
  const chat = document.getElementById("chat");
  const body = document.getElementById("chat-body");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const sendBtn = form?.querySelector("button");
  if (!chat || !body || !form) return;

  let sessionId = `s${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36)}`;
  let state = "start";
  let context = { brand: null, modelId: null, modelName: null };
  let modelsByBrand = { MG: [], Maxus: [] };
  let modelsLoaded = false;
  let history = []; // for free-text mode → server LLM

  // ---------- open / close ----------
  function open() {
    chat.classList.remove("is-collapsing");
    chat.classList.add("is-open");
    chat.setAttribute("aria-hidden", "false");
    if (!body.children.length) renderStart();
  }
  function close() {
    if (!chat.classList.contains("is-open")) return;
    chat.classList.remove("is-open");
    chat.classList.add("is-collapsing");
    chat.setAttribute("aria-hidden", "true");
    // Drop the collapsing flair class once the rail flare animation has run
    setTimeout(() => chat.classList.remove("is-collapsing"), 900);
  }

  document.getElementById("open-chat")?.addEventListener("click", open);
  document.getElementById("close-chat")?.addEventListener("click", close);
  document.getElementById("chat-rail")?.addEventListener("click", open);
  document.getElementById("chat-overlay")?.addEventListener("click", close);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && chat.classList.contains("is-open")) close(); });

  // ---------- auto-open on every page load, collapse after 3s ----------
  // Defer the first paint a tick so the rail renders in its starting state,
  // then the panel slides in over it. After 3 seconds we auto-collapse —
  // unless the user has already engaged with the chat (clicked a chip /
  // sent a message), in which case we leave it open.
  requestAnimationFrame(() => {
    open();
    setTimeout(() => {
      if (state === "start" && !history.length) close();
    }, 3000);
  });

  document.addEventListener("click", (e) => {
    const trigger = e.target.closest("[data-open-chat]");
    if (!trigger) return;
    if (trigger.dataset.chatFlow === "servicios") {
      reset();
      open();
      enterServicios();
    } else if (trigger.dataset.chatModel) {
      const id = trigger.dataset.chatModel;
      reset();
      open();
      // We don't know model name yet without lookup; let lookup happen via models load.
      ensureModels().then(() => {
        const all = [...modelsByBrand.MG, ...modelsByBrand.Maxus];
        const m = all.find(x => x.id === id);
        if (m) selectModel(m);
        else renderStart();
      });
    } else {
      open();
    }
    trigger.closest("dialog")?.close();
  });

  // ---------- helpers ----------
  function reset() {
    body.innerHTML = "";
    state = "start";
    context = { brand: null, modelId: null, modelName: null };
    history = [];
    input.value = "";
    input.disabled = true;
    sendBtn.disabled = true;
  }

  function botBubble(html) {
    const tpl = document.getElementById("tpl-msg-bot");
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.innerHTML = html;
    body.appendChild(node);
    scrollToBottom();
    return node;
  }
  function userBubble(text) {
    const tpl = document.getElementById("tpl-msg-user");
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.textContent = text;
    body.appendChild(node);
    scrollToBottom();
    return node;
  }
  function chips(items, onPick) {
    const wrap = document.createElement("div");
    wrap.className = "chat__chips";
    items.forEach(it => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "chip"; b.textContent = it.label;
      b.addEventListener("click", () => {
        wrap.querySelectorAll(".chip").forEach(c => c.disabled = true);
        userBubble(it.label);
        onPick(it.value, it);
      });
      wrap.appendChild(b);
    });
    body.appendChild(wrap);
    scrollToBottom();
    return wrap;
  }
  function scrollToBottom() { body.scrollTop = body.scrollHeight; }
  function pause(ms) { return new Promise(r => setTimeout(r, ms)); }

  function escapeHtml(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c])); }

  // ---------- start ----------
  async function renderStart() {
    state = "start";
    botBubble(`<p>¡Hola! Soy tu asesor de <strong>Holly Import</strong>. ¿En qué te puedo ayudar hoy?</p>`);
    chips([
      { label: "Compra", value: "compra" },
      { label: "Servicios", value: "servicios" },
      { label: "Repuestos", value: "repuestos" },
    ], (v) => {
      if (v === "compra") enterCompra();
      else if (v === "servicios") enterServicios();
      else enterRepuestos();
    });
  }

  // ---------- compra flow ----------
  async function ensureModels() {
    if (modelsLoaded) return;
    try {
      const r = await fetch(BASE + "/api/models");
      const j = await r.json();
      (j.models || []).forEach(m => {
        if (m.brand === "MG") modelsByBrand.MG.push(m);
        else if (m.brand === "Maxus") modelsByBrand.Maxus.push(m);
      });
      modelsLoaded = true;
    } catch { /* leave empty; we'll fall through */ }
  }

  async function enterCompra() {
    state = "compra-brand";
    await pause(300);
    botBubble(`<p>¡Excelente! ¿Qué marca te interesa?</p>`);
    chips([
      { label: "MG", value: "MG" },
      { label: "Maxus", value: "Maxus" },
    ], async (brand) => {
      context.brand = brand;
      await ensureModels();
      enterCompraModel(brand);
    });
  }

  async function enterCompraModel(brand) {
    state = "compra-model";
    await pause(250);
    botBubble(`<p>¿Cuál modelo de <strong>${escapeHtml(brand)}</strong> te llama la atención?</p>`);
    const list = modelsByBrand[brand] || [];
    if (!list.length) {
      botBubble(`<p>No pude cargar la lista de modelos. Un asesor te contactará para ayudarte.</p>`);
      showLeadForm();
      return;
    }
    chips(list.map(m => ({ label: m.name, value: m.id, model: m })), (_v, it) => {
      selectModel(it.model);
    });
  }

  async function selectModel(model) {
    context.modelId = model.id;
    context.modelName = model.name;
    context.brand = model.brand;
    state = "compra-confirm";
    await pause(250);
    botBubble(`
      <p><strong>${escapeHtml(model.name)}</strong> — ${escapeHtml(model.tagline || "")}</p>
      <p>Motor: ${escapeHtml(model.specs?.motor || "")} · Potencia: ${escapeHtml(model.specs?.potencia || "")}</p>
    `);
    await pause(200);
    botBubble(`<p>¿Quieres que un asesor de Holly Import te contacte para conversar sobre el ${escapeHtml(model.name)}?</p>`);
    chips([
      { label: "Sí, contáctenme", value: "yes" },
      { label: "Tengo otra pregunta", value: "free" },
    ], (v) => {
      if (v === "yes") showLeadForm();
      else enterFreeText(`El cliente está interesado en el ${context.modelName} (${context.brand}).`);
    });
  }

  function showLeadForm() {
    state = "lead-form";
    const tpl = document.getElementById("tpl-lead-form");
    const node = tpl.content.firstElementChild.cloneNode(true);
    body.appendChild(node);
    scrollToBottom();
    node.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(node);
      const data = Object.fromEntries(fd.entries());
      node.querySelector("button[type=submit]").disabled = true;
      try {
        const r = await fetch(BASE + "/api/lead", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            flow: "compra",
            brand: context.brand || "",
            model_id: context.modelId || "",
            name: data.name,
            phone: data.phone,
            contact_pref: data.contact_pref || "call_text",
          }),
        });
        if (!r.ok) throw new Error("err");
        node.replaceWith(Object.assign(document.createElement("div"), {
          className: "chat__msg chat__msg--bot",
          innerHTML: "<p>¡Listo! Un asesor de Holly Import te contactará pronto.</p>"
        }));
        scrollToBottom();
        await pause(400);
        botBubble(`<p>¿Algo más en lo que pueda ayudarte?</p>`);
        chips([
          { label: "Otra consulta", value: "free" },
          { label: "Cerrar chat", value: "close" },
        ], (v) => v === "free" ? enterFreeText("Lead capturado. Conversación libre.") : close());
      } catch {
        node.querySelector("button[type=submit]").disabled = false;
        botBubble(`<p>No se pudo enviar. Intenta de nuevo o llámanos directamente.</p>`);
      }
    });
  }

  // ---------- servicios flow ----------
  async function enterServicios() {
    state = "servicios-confirm";
    await pause(300);
    botBubble(`<p>Perfecto. ¿Te gustaría agendar un servicio para tu vehículo?</p>`);
    chips([
      { label: "Sí, agendar", value: "yes" },
      { label: "Tengo una pregunta", value: "free" },
    ], (v) => {
      if (v === "yes") showServiceForm();
      else enterFreeText("El cliente quiere preguntas sobre el taller / servicio técnico.");
    });
  }

  function showServiceForm() {
    state = "service-form";
    const tpl = document.getElementById("tpl-service-form");
    const node = tpl.content.firstElementChild.cloneNode(true);
    body.appendChild(node);
    // sensible default date: tomorrow
    const t = new Date(); t.setDate(t.getDate() + 1);
    node.querySelector("input[name=preferred_date]").value = t.toISOString().slice(0, 10);
    scrollToBottom();
    node.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(node);
      const data = Object.fromEntries(fd.entries());
      node.querySelector("button[type=submit]").disabled = true;
      try {
        const r = await fetch(BASE + "/api/service", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, ...data }),
        });
        if (!r.ok) throw new Error("err");
        node.replaceWith(Object.assign(document.createElement("div"), {
          className: "chat__msg chat__msg--bot",
          innerHTML: "<p>¡Listo! Tu cita queda registrada y un asesor confirmará la disponibilidad.</p>"
        }));
        scrollToBottom();
        await pause(400);
        botBubble(`<p>¿Necesitas algo más?</p>`);
        chips([
          { label: "Otra consulta", value: "free" },
          { label: "Cerrar chat", value: "close" },
        ], (v) => v === "free" ? enterFreeText("Servicio agendado. Conversación libre.") : close());
      } catch {
        node.querySelector("button[type=submit]").disabled = false;
        botBubble(`<p>No se pudo agendar. Intenta de nuevo o llámanos directamente.</p>`);
      }
    });
  }

  // ---------- repuestos flow ----------
  async function enterRepuestos() {
    state = "repuestos-brand";
    await pause(300);
    botBubble(`<p>Perfecto. ¿Para qué marca necesitas el repuesto?</p>`);
    chips([
      { label: "MG", value: "MG" },
      { label: "Maxus", value: "Maxus" },
      { label: "Toyota", value: "Toyota" },
      { label: "Otra marca", value: "Otro" },
    ], (brand) => {
      context.brand = brand;
      showRepuestosForm();
    });
  }

  function showRepuestosForm() {
    state = "repuestos-form";
    const tpl = document.getElementById("tpl-repuestos-form");
    const node = tpl.content.firstElementChild.cloneNode(true);
    body.appendChild(node);
    scrollToBottom();
    node.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(node);
      const data = Object.fromEntries(fd.entries());
      node.querySelector("button[type=submit]").disabled = true;
      const notes = `Vehículo: ${data.vehicle}\nRepuesto: ${data.part}`;
      try {
        const r = await fetch(BASE + "/api/lead", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            flow: "repuestos",
            brand: context.brand || "",
            name: data.name,
            phone: data.phone,
            contact_pref: data.contact_pref || "call_text",
            notes,
          }),
        });
        if (!r.ok) throw new Error("err");
        node.replaceWith(Object.assign(document.createElement("div"), {
          className: "chat__msg chat__msg--bot",
          innerHTML: "<p>¡Listo! Un asesor te contactará pronto con disponibilidad y precio.</p>"
        }));
        scrollToBottom();
        await pause(400);
        botBubble(`<p>¿Algo más en lo que pueda ayudarte?</p>`);
        chips([
          { label: "Otra consulta", value: "free" },
          { label: "Cerrar chat", value: "close" },
        ], (v) => v === "free" ? enterFreeText("Repuesto solicitado. Conversación libre.") : close());
      } catch {
        node.querySelector("button[type=submit]").disabled = false;
        botBubble(`<p>No se pudo enviar. Intenta de nuevo o llámanos directamente.</p>`);
      }
    });
  }

  // ---------- free text → LLM ----------
  function enterFreeText(contextNote = "") {
    state = "free";
    history = []; // start fresh for this LLM mini-session
    input.disabled = false;
    sendBtn.disabled = false;
    input.placeholder = "Escribe tu pregunta…";
    botBubble(`<p>Cuéntame, ¿qué te gustaría saber?</p>`);
    form.dataset.contextNote = contextNote;
    input.focus();
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    userBubble(text);
    history.push({ role: "user", content: text });
    sendBtn.disabled = true; input.disabled = true;
    const thinking = botBubble("<p><em>Escribiendo…</em></p>");
    try {
      const r = await fetch(BASE + "/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          messages: history.slice(-12),
          context: form.dataset.contextNote || "",
        }),
      });
      const j = await r.json();
      thinking.innerHTML = `<p>${escapeHtml(j.reply || "Disculpa, intenta de nuevo.")}</p>`;
      if (j.reply) history.push({ role: "assistant", content: j.reply });
    } catch {
      thinking.innerHTML = "<p>Disculpa, hubo un problema. Intenta de nuevo.</p>";
    } finally {
      sendBtn.disabled = false; input.disabled = false;
      input.focus();
      scrollToBottom();
    }
  });
})();
