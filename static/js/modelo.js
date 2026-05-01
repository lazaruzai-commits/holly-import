// Per-model page interactions:
//   - Equipamiento destacado: hovering / focusing a feature swaps the
//     preview image on the right (manilla-folder behaviour)
//   - Gallery: tab switching (Exterior / Interior / Find your Style),
//     pauses any visualizer videos when leaving the Style tab
//   - Lightbox: clicking a gallery photo opens a fullscreen overlay
(() => {
  // ---------- features hover preview ----------
  const items = document.querySelectorAll(".features__item");
  const preview = document.querySelector(".features__preview-img");
  const caption = document.getElementById("features-caption");
  if (items.length && preview) {
    function activate(item) {
      items.forEach(i => {
        const on = i === item;
        i.classList.toggle("is-active", on);
        i.tabIndex = on ? 0 : -1;
      });
      const src = item.dataset.img;
      const cap = item.dataset.caption || "";
      if (src && preview.getAttribute("src") !== src) {
        preview.classList.add("is-swapping");
        const tmp = new Image();
        tmp.onload = () => {
          preview.src = src;
          // double rAF to let the browser paint before fading back in
          requestAnimationFrame(() => requestAnimationFrame(() => {
            preview.classList.remove("is-swapping");
          }));
        };
        tmp.src = src;
      }
      if (caption) caption.textContent = cap;
    }
    items.forEach(item => {
      item.addEventListener("mouseenter", () => activate(item));
      item.addEventListener("focus", () => activate(item));
      item.addEventListener("click", () => activate(item));
      item.addEventListener("keydown", (e) => {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          e.preventDefault();
          const arr = Array.from(items);
          const i = arr.indexOf(item);
          const next = arr[(i + (e.key === "ArrowDown" ? 1 : -1) + arr.length) % arr.length];
          next.focus();
        }
      });
    });
  }

  // ---------- gallery tabs ----------
  const gallery = document.getElementById("gallery");
  if (gallery) {
    const tabs = Array.from(gallery.querySelectorAll(".gallery__tab"));
    const panes = Array.from(gallery.querySelectorAll(".gallery__pane"));
    function showTab(name) {
      tabs.forEach(t => {
        const on = t.dataset.tab === name;
        t.classList.toggle("is-active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      panes.forEach(p => {
        const on = p.dataset.pane === name;
        p.classList.toggle("is-active", on);
        p.hidden = !on;
        if (!on) {
          p.querySelectorAll("video").forEach(v => v.pause());
        }
      });
    }
    tabs.forEach(t => t.addEventListener("click", () => showTab(t.dataset.tab)));
  }

  // ---------- lightbox for gallery photos ----------
  const photos = document.querySelectorAll(".gallery__photo");
  if (photos.length) {
    let overlay = null;
    function open(src) {
      if (!overlay) {
        overlay = document.createElement("div");
        overlay.className = "lightbox";
        overlay.innerHTML = `<button class="lightbox__close" type="button" aria-label="Cerrar">×</button><img class="lightbox__img" alt="">`;
        overlay.addEventListener("click", (e) => {
          if (e.target === overlay || e.target.classList.contains("lightbox__close")) close();
        });
        document.body.appendChild(overlay);
      }
      overlay.querySelector(".lightbox__img").src = src;
      overlay.classList.add("is-open");
      document.body.style.overflow = "hidden";
    }
    function close() {
      overlay?.classList.remove("is-open");
      document.body.style.overflow = "";
    }
    photos.forEach(p => p.addEventListener("click", (e) => {
      e.preventDefault();
      open(p.getAttribute("href"));
    }));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && overlay?.classList.contains("is-open")) close();
    });
  }
})();
