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

// ── Lazy loader per view ──────────────────────────────────────────────────────
// Data tab hanya diambil saat tab-nya pertama kali dibuka, mengikuti pola
// _ensureChatReady / _ensureOfficialStatisticsReady. Tanpa ini, bootstrap harus
// menunggu /api/berita dan stream AI Insight sebelum overview bisa tampil.

async function _ensureBeritaReady() {
  if (_beritaLoaded || _beritaLoading) return;
  if (typeof loadBerita !== "function") return;
  _beritaLoading = true;
  try {
    await loadBerita();
    _beritaLoaded = true;
  } finally {
    _beritaLoading = false;
  }
}

function _ensureAIInsightsReady() {
  if (_aiInsightsLoaded) return;
  if (typeof loadAIInsights !== "function") return;
  _aiInsightsLoaded = true;
  loadAIInsights();
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

  if (view === "data") {
    _ensureBeritaReady();
  }

  if (view === "insight") {
    _ensureAIInsightsReady();
  }

  if (view === "chat") {
    _ensureChatReady();
    const input = document.getElementById("chatInput");
    if (input) {
      setTimeout(() => input.focus(), 80);
    }
  }

  if (view === "official-statistics" && typeof _ensureOfficialStatisticsReady === "function") {
    _ensureOfficialStatisticsReady();
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
