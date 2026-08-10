// Panduan halaman Audit Relevance: panel "Apa ini?" (collapsible) + modal
// bantuan (Panduan/Pintasan, dibuka tombol "?" atau tombol di panel) + hint
// kontekstual per tab.
//
// Status buka/tutup panel disimpan di localStorage, BUKAN di user_activity_state
// (fitur feedback):
//   - Ini murni preferensi tampilan; kehilangannya cuma berarti satu klik ekstra.
//   - Halaman disajikan sebagai file statis (routes/pages.py send_from_directory),
//     jadi status dari server baru tiba SETELAH render pertama -> panel akan
//     berkedip terbuka lalu menutup sendiri. localStorage terbaca sinkron
//     sebelum paint pertama, jadi tidak berkedip.
//   - user_activity_state dipakai menghitung aktivitas bermakna untuk memicu
//     prompt feedback; menulis toggle kosmetik ke sana mengotori data itu.
// Versi di-bump kalau isi panduan berubah materiil -> panduan terbuka sekali lagi.

const GUIDE_STORAGE_KEY = "wartos.relevance.guide";
const GUIDE_VERSION = 1;

const REL_TAB_HINTS = {
  uncertainty: "Kasus paling meragukan (skor dekat ambang 50). Labeli di sini dulu — dampaknya terbesar.",
  audit: "Sampel acak berstrata. Labeli <strong>seluruh</strong> sampel — hanya dari sini angka akurasi tak bias.",
  failed: "Gerbang error/timeout, belum pernah berhasil dinilai. Triase: yang relevan klasifikasi ulang.",
  labeled: "Semua yang sudah dilabeli manusia. Dipakai sebagai set uji kering (golden set) prompt.",
  disagreement: "Mesin ≠ manusia. Bahan few-shot terbaik untuk memperbaiki prompt.",
  all: "Seluruh korpus berskor, tanpa filter. Untuk penelusuran, bukan untuk pelabelan massal.",
};

function _readGuideState() {
  try {
    const raw = JSON.parse(localStorage.getItem(GUIDE_STORAGE_KEY) || "{}");
    if (Number(raw.version) !== GUIDE_VERSION) return { collapsed: false };
    return { collapsed: Boolean(raw.collapsed) };
  } catch {
    return { collapsed: false };
  }
}

function _writeGuideState(collapsed) {
  try {
    localStorage.setItem(GUIDE_STORAGE_KEY, JSON.stringify({ version: GUIDE_VERSION, collapsed }));
  } catch {
    /* mode privat / storage penuh -- abaikan, bukan hal kritis */
  }
}

function setRelTabHint(mode) {
  const el = document.getElementById("relTabHint");
  if (el) el.innerHTML = REL_TAB_HINTS[mode] || "";
}

function openRelevanceHelp(tab = "panduan") {
  const modal = document.getElementById("relHelpModal");
  if (!modal) return;
  modal.querySelectorAll(".rel-help-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tab);
  });
  modal.querySelectorAll(".rel-help-pane").forEach((pane) => {
    pane.classList.toggle("is-hidden", pane.dataset.pane !== tab);
  });
  modal.classList.remove("hidden");
}

function closeRelevanceHelp() {
  document.getElementById("relHelpModal")?.classList.add("hidden");
}

function initRelevanceGuide() {
  const panel = document.getElementById("relGuide");
  const toggle = document.getElementById("relGuideToggle");
  if (panel && toggle) {
    const apply = (collapsed) => {
      panel.dataset.collapsed = String(collapsed);
      toggle.setAttribute("aria-expanded", String(!collapsed));
    };
    apply(_readGuideState().collapsed);

    toggle.addEventListener("click", () => {
      const next = panel.dataset.collapsed !== "true";
      apply(next);
      _writeGuideState(next);
    });

    panel.querySelectorAll("[data-help-tab]").forEach((btn) => {
      btn.addEventListener("click", () => openRelevanceHelp(btn.dataset.helpTab));
    });
  }

  const helpModal = document.getElementById("relHelpModal");
  if (helpModal) {
    helpModal.querySelectorAll(".rel-help-tab").forEach((btn) => {
      btn.addEventListener("click", () => openRelevanceHelp(btn.dataset.tab));
    });
    helpModal.addEventListener("click", (e) => {
      if (e.target === helpModal) closeRelevanceHelp();
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.key !== "?" || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.target.closest("input, textarea, select, [contenteditable='true']")) return;
    e.preventDefault();
    openRelevanceHelp("pintasan");
  });
}
