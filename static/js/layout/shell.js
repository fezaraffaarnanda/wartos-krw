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
