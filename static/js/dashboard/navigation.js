function _closeSidebar() {
  const shell = document.getElementById("appShell");
  if (shell) shell.classList.remove("sidebar-open");
}

function _setViewHeader(view) {
  const titleEl = document.getElementById("viewTitle");
  const subtitleEl = document.getElementById("viewSubtitle");
  const meta = VIEW_META[view] || VIEW_META.overview;
  if (titleEl) titleEl.textContent = meta.title;
  if (subtitleEl) subtitleEl.textContent = meta.subtitle;
}

function _setActiveMenu(view) {
  document.querySelectorAll(".sidebar-link[data-view]").forEach((btn) => {
    const active = btn.dataset.view === view;
    btn.classList.toggle("active", active);
    if (active) {
      btn.setAttribute("aria-current", "page");
    } else {
      btn.removeAttribute("aria-current");
    }
  });
}

function _setActiveView(view) {
  _activeView = view;
  _setViewHeader(view);
  _setActiveMenu(view);
  document.body.classList.toggle("chat-view-lock", view === "chat");

  document.querySelectorAll(".app-view").forEach((el) => {
    const ownsView = el.dataset.view === view;
    el.classList.toggle("view-hidden", !ownsView);
  });

  const main = document.getElementById("mainContent");
  const appContent = document.querySelector(".app-content");
  if (main) {
    main.classList.toggle("is-chat-mode", view === "chat");
  }
  if (appContent) {
    appContent.classList.toggle("chat-view-active", view === "chat");
  }

  if (view === "chat") {
    _ensureChatReady();
    const input = document.getElementById("chatInput");
    if (input) {
      setTimeout(() => input.focus(), 80);
    }
  }
}

function _viewFromHash() {
  const raw = (window.location.hash || "").replace("#", "").trim().toLowerCase();
  if (!raw) return "overview";
  return VIEW_META[raw] ? raw : "overview";
}

function _openView(view, { updateHash = true } = {}) {
  if (!VIEW_META[view]) view = "overview";
  _setActiveView(view);
  if (updateHash) {
    window.location.hash = view === "overview" ? "" : view;
  }
  _closeSidebar();
}

function initSidebarNavigation() {
  document.querySelectorAll(".sidebar-link[data-view]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const view = btn.dataset.view || "overview";
      _openView(view, { updateHash: true });
    });
  });

  window.addEventListener("hashchange", () => {
    _openView(_viewFromHash(), { updateHash: false });
  });

  _openView(_viewFromHash(), { updateHash: false });
}
