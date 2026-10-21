// Hero carousel with video slides.
//
// Bandwidth policy (the home page used to pull ~30 MB of video on load):
//   - The markup gives only the first slide a real `src`; every other slide
//     carries `data-src` plus a poster image, so it costs nothing until shown.
//   - When a slide becomes active we attach its src and play it. We also
//     attach the *next* slide's src at that moment (preload="auto") so the
//     following transition is seamless — but never more than one ahead.
//   - On small screens or when the browser asks to save data we skip video
//     entirely: slides show their posters and advance on a timer.
(() => {
  const root = document.getElementById("hero-slider");
  if (!root) return;
  const slides = Array.from(root.querySelectorAll(".hero-slide"));
  const dots   = Array.from(root.querySelectorAll(".hero-slider__dot"));
  const videos = slides.map(s => s.querySelector("video"));
  if (!slides.length) return;

  const conn = navigator.connection || {};
  const POSTERS_ONLY = window.matchMedia("(max-width: 600px)").matches
                    || conn.saveData === true
                    || /(^|-)2g$/.test(conn.effectiveType || "");
  const POSTER_SLIDE_MS = 6000;   // how long a poster-only slide stays up
  const STALL_MS = 30000;         // safety net if a video never fires "ended"

  let idx = 0;
  let timer = null;

  // Attach a slide's video source (once). Returns true if the slide has video.
  function attach(i, preload) {
    const v = videos[i];
    if (!v) return false;
    if (!v.poster && v.dataset.poster) v.poster = v.dataset.poster;   // posters are lazy too
    if (!v.src && v.dataset.src) {
      v.preload = preload || "auto";
      v.src = v.dataset.src;
      v.load();
    }
    return !!v.src;
  }

  videos.forEach((v, i) => {
    if (!v) return;
    v.addEventListener("ended", () => { if (i === idx) nextSlide(); });
    v.addEventListener("error", () => {
      v.style.display = "none";          // leaves the poster/backdrop visible
      if (i === idx) nextSlide();
    });
    if (POSTERS_ONLY) {
      v.removeAttribute("autoplay");
      v.removeAttribute("src");
      v.preload = "none";
      if (!v.poster && v.dataset.poster) v.poster = v.dataset.poster;
    }
  });

  function play(i) {
    if (POSTERS_ONLY) return;
    if (!attach(i)) return;
    const v = videos[i];
    try { v.currentTime = 0; } catch (e) {}
    v.play().catch(() => {});            // autoplay may be refused; poster stays
    // Warm the next slide so the transition doesn't start from a blank frame.
    attach((i + 1) % slides.length, "auto");
  }

  function activate(next) {
    next = (next + slides.length) % slides.length;
    if (next === idx) return;
    slides[idx].classList.remove("is-active");
    dots[idx]?.classList.remove("is-active");
    videos[idx]?.pause();

    idx = next;
    slides[idx].classList.add("is-active");
    dots[idx]?.classList.add("is-active");
    play(idx);
  }

  function nextSlide() { activate(idx + 1); startAuto(); }

  // Poster-only mode advances on a fixed timer; video mode uses "ended" with a
  // long stall timeout as a fallback.
  function startAuto() {
    stopAuto();
    timer = setTimeout(() => activate(idx + 1) || startAuto(),
                       POSTERS_ONLY ? POSTER_SLIDE_MS : STALL_MS);
  }
  function stopAuto() { if (timer) { clearTimeout(timer); timer = null; } }

  // Manual controls
  root.querySelector("[data-slider-prev]")?.addEventListener("click", () => { activate(idx - 1); startAuto(); });
  root.querySelector("[data-slider-next]")?.addEventListener("click", () => { activate(idx + 1); startAuto(); });
  dots.forEach(d => d.addEventListener("click", () => {
    activate(parseInt(d.dataset.sliderGo, 10) || 0);
    startAuto();
  }));

  root.addEventListener("mouseenter", stopAuto);
  root.addEventListener("mouseleave", startAuto);
  root.addEventListener("focusin", stopAuto);
  root.addEventListener("focusout", startAuto);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stopAuto();
      videos[idx]?.pause();
    } else {
      if (!POSTERS_ONLY) videos[idx]?.play().catch(() => {});
      startAuto();
    }
  });

  root.tabIndex = 0;
  root.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft")  { activate(idx - 1); startAuto(); }
    if (e.key === "ArrowRight") { activate(idx + 1); startAuto(); }
  });

  // touch swipe
  let touchX = null;
  root.addEventListener("touchstart", (e) => { touchX = e.touches[0].clientX; stopAuto(); }, { passive: true });
  root.addEventListener("touchend", (e) => {
    if (touchX == null) return;
    const dx = e.changedTouches[0].clientX - touchX;
    if (Math.abs(dx) > 40) activate(idx + (dx < 0 ? 1 : -1));
    touchX = null; startAuto();
  });

  // Kick off. The first slide already has its src + autoplay from the markup;
  // play() here mainly warms slide 2.
  play(0);
  startAuto();
})();
