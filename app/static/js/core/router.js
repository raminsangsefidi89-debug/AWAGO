/** Tiny hash router with deep links: #/pair/EUR-USD, #/models, ... */

const routes = [];
let current = null;

export function route(pattern, handler) {
  // pattern like "pair/:symbol" — :name captures one segment
  const parts = pattern.split("/").map((p) => (p.startsWith(":") ? { param: p.slice(1) } : p));
  routes.push({ parts, handler, pattern });
}

export function navigate(path) {
  window.location.hash = `#/${path.replace(/^#?\/?/, "")}`;
}

function match(hashPath) {
  const segs = hashPath.replace(/^#\/?/, "").split("/").filter(Boolean);
  for (const r of routes) {
    if (r.parts.length !== segs.length) continue;
    const params = {};
    let ok = true;
    r.parts.forEach((part, i) => {
      if (typeof part === "string") {
        if (part !== segs[i]) ok = false;
      } else {
        params[part.param] = decodeURIComponent(segs[i]);
      }
    });
    if (ok) return { handler: r.handler, params, pattern: r.pattern };
  }
  return null;
}

export function startRouter(mountEl, fallback) {
  async function render() {
    const found = match(window.location.hash || "#/");
    const target = found || { handler: fallback, params: {} };
    if (current && typeof current.cleanup === "function") {
      try {
        current.cleanup();
      } catch {
        /* page cleanup must never break navigation */
      }
    }
    mountEl.setAttribute("aria-busy", "true");
    mountEl.innerHTML = '<div class="skeleton skeleton-hero"></div>';
    try {
      current = await target.handler(target.params, mountEl);
    } catch (err) {
      mountEl.innerHTML = `<div class="error-state" role="alert"><strong>خطا در بارگذاری صفحه</strong><p>${String(err.message || err)}</p></div>`;
    }
    mountEl.setAttribute("aria-busy", "false");
    // focus management for accessibility
    const h = mountEl.querySelector("h2");
    if (h) {
      h.setAttribute("tabindex", "-1");
      h.focus({ preventScroll: true });
    }
    document.querySelectorAll("nav a").forEach((a) => {
      const active = a.getAttribute("href") === `#/${(window.location.hash || "#/").replace(/^#\/?/, "")}`;
      a.classList.toggle("active", active);
      if (active) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
  }
  window.addEventListener("hashchange", render);
  render();
}
