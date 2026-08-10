// Daftar sumber berita — SELALU dari server (GET /api/sources), jangan
// hardcode. Backend: config/region.py::NEWS_SOURCES.
let NEWS_SOURCES = []; // [{key, label}]
let SOURCE_KEYS = []; // [key, ...]
let SOURCE_LABELS_UI = {}; // {key: label}

async function loadNewsSources() {
  if (NEWS_SOURCES.length) return NEWS_SOURCES;
  try {
    const res = await fetch("/api/sources");
    if (res.status === 401) {
      window.location.href = "/login";
      return [];
    }
    const json = await res.json();
    if (json.status !== "ok") throw new Error(json.message || "gagal memuat sumber");
    NEWS_SOURCES = json.data || [];
  } catch (err) {
    console.error("Gagal memuat daftar sumber berita:", err);
    NEWS_SOURCES = [];
  }
  SOURCE_KEYS = NEWS_SOURCES.map((s) => s.key);
  SOURCE_LABELS_UI = Object.fromEntries(NEWS_SOURCES.map((s) => [s.key, s.label]));
  return NEWS_SOURCES;
}

function renderSourceChips(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = NEWS_SOURCES.length
    ? NEWS_SOURCES.map((s) => `<span class="welcome-chip">${escapeHtml(s.label)}</span>`).join("")
    : `<span class="welcome-chip">Daftar sumber tidak tersedia</span>`;
}

function renderSourceCount(elId) {
  const el = document.getElementById(elId);
  if (el) el.textContent = String(NEWS_SOURCES.length || "—");
}

function renderSourceListInline(elId) {
  const el = document.getElementById(elId);
  if (!el) return;
  const names = NEWS_SOURCES.map((s) => s.label);
  el.textContent =
    names.length <= 1
      ? names[0] || "—"
      : `${names.slice(0, -1).join(", ")}, dan ${names[names.length - 1]}`;
}

function renderProgressRows(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = NEWS_SOURCES.map(
    (s) => `
    <div class="progress-row" data-source-key="${escapeHtml(s.key)}">
      <div class="progress-label">
        <span class="progress-source">${escapeHtml(s.label)}</span>
        <span class="progress-status" id="status-${escapeHtml(s.key)}">Menunggu...</span>
      </div>
      <div class="progress-bar-track">
        <div class="progress-bar-fill" id="bar-${escapeHtml(s.key)}" style="width: 0%"></div>
      </div>
      <span class="progress-count" id="count-${escapeHtml(s.key)}">0</span>
    </div>`,
  ).join("");
}
