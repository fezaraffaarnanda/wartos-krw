const PAGE_LOADING_OVERLAY_ID = "pageLoadingOverlay";

function getPageLoadingOverlay() {
  return document.getElementById(PAGE_LOADING_OVERLAY_ID);
}

function setPageLoadingOverlayVisible(isVisible, options = {}) {
  const overlay = getPageLoadingOverlay();
  if (!overlay) return;

  const title = overlay.querySelector(".page-loading-title");
  const subtitle = overlay.querySelector(".page-loading-subtitle");

  if (typeof options.title === "string" && title) {
    title.textContent = options.title;
  }

  if (typeof options.subtitle === "string" && subtitle) {
    subtitle.textContent = options.subtitle;
  }

  overlay.hidden = !isVisible;
  document.body.setAttribute("aria-busy", isVisible ? "true" : "false");
}

function showPageLoadingOverlay(options = {}) {
  setPageLoadingOverlayVisible(true, options);
}

function hidePageLoadingOverlay() {
  setPageLoadingOverlayVisible(false);
}

function initAppShell({ storageKey = "bps_sidebar_collapsed" } = {}) {
  const shell = document.getElementById("appShell");
  const toggle = document.getElementById("sidebarToggle");
  const overlay = document.getElementById("sidebarOverlay");
  if (!shell || !toggle) return;

  const isMobile = () => window.matchMedia("(max-width: 1100px)").matches;

  const applyCollapsed = (collapsed) => {
    shell.classList.toggle("sidebar-collapsed", collapsed);
    toggle.setAttribute("aria-label", collapsed ? "Buka sidebar" : "Tutup sidebar");
    toggle.title = collapsed ? "Buka sidebar" : "Tutup sidebar";
  };

  const storedCollapsed = localStorage.getItem(storageKey) === "1";
  applyCollapsed(storedCollapsed && !isMobile());

  toggle.addEventListener("click", () => {
    if (isMobile()) {
      shell.classList.toggle("sidebar-open");
      return;
    }

    const next = !shell.classList.contains("sidebar-collapsed");
    applyCollapsed(next);
    localStorage.setItem(storageKey, next ? "1" : "0");
  });

  overlay?.addEventListener("click", () => {
    shell.classList.remove("sidebar-open");
  });

  window.addEventListener("resize", () => {
    if (isMobile()) {
      applyCollapsed(false);
      return;
    }

    shell.classList.remove("sidebar-open");
    applyCollapsed(localStorage.getItem(storageKey) === "1");
  });
}
