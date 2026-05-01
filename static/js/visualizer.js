// Per-model "Encuentra tu estilo" colour visualizer.
// All colour videos exist in the DOM stacked behind the active one. Picking
// a chip swaps the .is-active class so the new video fades in. Inactive
// videos drop to preload="metadata" to avoid downloading every clip up
// front; they switch to "auto" the first time they're picked.
(() => {
  const root = document.getElementById("visualizer");
  if (!root) return;
  const videos = Array.from(root.querySelectorAll(".visualizer__video"));
  const chips  = Array.from(root.querySelectorAll(".visualizer__chip"));
  const nameEl = document.getElementById("visualizer-name");
  const pp     = document.getElementById("visualizer-pp");
  if (!videos.length || !chips.length) return;

  let active = videos[0];
  active.play().catch(() => {});

  function selectColor(colorKey) {
    const next = videos.find(v => v.dataset.color === colorKey);
    const chip = chips.find(c => c.dataset.color === colorKey);
    if (!next || !chip) return;
    chips.forEach(c => {
      const on = c === chip;
      c.classList.toggle("is-active", on);
      c.setAttribute("aria-checked", on ? "true" : "false");
    });
    if (next === active) return;
    next.preload = "auto";
    next.currentTime = 0;
    next.play().catch(() => {});
    next.classList.add("is-active");
    active.classList.remove("is-active");
    active.pause();
    active = next;
    if (nameEl) nameEl.textContent = chip.dataset.colorName;
    syncPlayPauseIcon();
  }

  chips.forEach(c => c.addEventListener("click", () => selectColor(c.dataset.color)));

  // Play / Pause toggle
  const playIcon  = pp?.querySelector('[data-icon="play"]');
  const pauseIcon = pp?.querySelector('[data-icon="pause"]');
  function syncPlayPauseIcon() {
    if (!pp) return;
    const playing = !active.paused;
    if (playIcon)  playIcon.style.display  = playing ? "none" : "";
    if (pauseIcon) pauseIcon.style.display = playing ? "" : "none";
    pp.setAttribute("aria-label", playing ? "Pausar video" : "Reproducir video");
  }
  pp?.addEventListener("click", () => {
    if (active.paused) active.play().catch(() => {});
    else active.pause();
    syncPlayPauseIcon();
  });
  videos.forEach(v => {
    v.addEventListener("play", syncPlayPauseIcon);
    v.addEventListener("pause", syncPlayPauseIcon);
  });
  syncPlayPauseIcon();
})();
