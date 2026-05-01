// Hero carousel with video slides.
// Behaviour:
//   - All <video> slides start preloading on page load (preload="auto")
//   - Each video buffers up to ~15 seconds, then we hint the browser to stop
//     by setting preload="metadata" so we don't waste bandwidth on slides the
//     user may never watch
//   - The active slide keeps preload="auto" and plays
//   - On slide change: pause the old active, play the new active, and let the
//     newly-active video resume buffering past the 15-second mark
(() => {
  const root = document.getElementById("hero-slider");
  if (!root) return;
  const slides = Array.from(root.querySelectorAll(".hero-slide"));
  const dots   = Array.from(root.querySelectorAll(".hero-slider__dot"));
  const videos = slides.map(s => s.querySelector("video"));
  if (!slides.length) return;

  let idx = 0;
  let timer = null;
  let advanceInterval = null;
  const PRELOAD_TARGET_S = 15;

  // ---------- preload throttling ----------
  // Each video tracks whether its initial 15s buffer goal is reached. Once it
  // is, inactive videos drop to preload="metadata" to halt further download.
  videos.forEach((v, i) => {
    if (!v) return;
    v.dataset.bufferReached = "false";
    v.addEventListener("progress", () => {
      if (v.dataset.bufferReached === "true") return;
      if (!v.buffered || v.buffered.length === 0) return;
      const end = v.buffered.end(v.buffered.length - 1);
      if (end >= PRELOAD_TARGET_S) {
        v.dataset.bufferReached = "true";
        if (i !== idx) v.preload = "metadata";   // halt download on inactive
      }
    });
    // when a slide's video finishes, jump to the next slide so the carousel
    // is paced by content rather than a fixed timer
    v.addEventListener("ended", () => {
      if (i === idx) nextSlide();
    });
    v.addEventListener("error", () => {
      v.style.display = "none";
      if (i === idx) nextSlide();
    });
  });

  function activate(next) {
    next = (next + slides.length) % slides.length;
    if (next === idx) return;
    slides[idx].classList.remove("is-active");
    dots[idx]?.classList.remove("is-active");
    const oldVideo = videos[idx];
    if (oldVideo) oldVideo.pause();

    idx = next;
    slides[idx].classList.add("is-active");
    dots[idx]?.classList.add("is-active");
    const newVideo = videos[idx];
    if (newVideo) {
      newVideo.preload = "auto";              // resume aggressive buffering
      newVideo.dataset.bufferReached = "false";
      try { newVideo.currentTime = 0; } catch (e) {}   // start from the beginning
      // play() may reject on iOS without user interaction — that's fine,
      // the muted attribute should let it autoplay in modern browsers
      newVideo.play().catch(() => {});
    }
  }

  function nextSlide() { activate(idx + 1); }

  // Safety-net advance — if a video stalls or never fires "ended" (e.g. it's
  // still buffering when the user expects movement), this kicks the carousel
  // forward after 30s. Manual nav and the natural "ended" event reset it.
  function startAuto() { stopAuto(); timer = setTimeout(nextSlide, 30000); }
  function stopAuto()  { if (timer) { clearTimeout(timer); timer = null; } }

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
      videos[idx]?.play().catch(() => {});
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

  // Kick off: first video should be playing thanks to autoplay attribute
  videos[0]?.play().catch(() => {});
  startAuto();
})();
