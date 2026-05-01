// Hero carousel — auto-advances, pauses on hover, dots + arrow keys + swipe.
(() => {
  const root = document.getElementById("hero-slider");
  if (!root) return;
  const slides = Array.from(root.querySelectorAll(".hero-slide"));
  const dots   = Array.from(root.querySelectorAll(".hero-slider__dot"));
  if (!slides.length) return;

  let idx = 0;
  let timer = null;
  const INTERVAL = 6000;

  function go(next) {
    next = (next + slides.length) % slides.length;
    if (next === idx) return;
    slides[idx].classList.remove("is-active");
    dots[idx]?.classList.remove("is-active");
    idx = next;
    slides[idx].classList.add("is-active");
    dots[idx]?.classList.add("is-active");
  }
  const advance = () => go(idx + 1);

  function start() { stop(); timer = setInterval(advance, INTERVAL); }
  function stop()  { if (timer) { clearInterval(timer); timer = null; } }

  root.querySelector("[data-slider-prev]")?.addEventListener("click", () => { go(idx - 1); start(); });
  root.querySelector("[data-slider-next]")?.addEventListener("click", () => { go(idx + 1); start(); });
  dots.forEach(d => d.addEventListener("click", () => {
    go(parseInt(d.dataset.sliderGo, 10) || 0);
    start();
  }));

  root.addEventListener("mouseenter", stop);
  root.addEventListener("mouseleave", start);
  root.addEventListener("focusin", stop);
  root.addEventListener("focusout", start);
  document.addEventListener("visibilitychange", () => document.hidden ? stop() : start());

  // keyboard
  root.tabIndex = 0;
  root.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft")  { go(idx - 1); start(); }
    if (e.key === "ArrowRight") { go(idx + 1); start(); }
  });

  // touch swipe
  let touchX = null;
  root.addEventListener("touchstart", (e) => { touchX = e.touches[0].clientX; stop(); }, { passive: true });
  root.addEventListener("touchend", (e) => {
    if (touchX == null) return;
    const dx = e.changedTouches[0].clientX - touchX;
    if (Math.abs(dx) > 40) go(idx + (dx < 0 ? 1 : -1));
    touchX = null; start();
  });

  start();
})();
