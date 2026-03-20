let filteredData = [];
let currentPage = 1;
const PER_PAGE = 15;
let sortField = "date_parsed";
let sortAsc = false;
let currentUser = null;
let _activeView = "overview";
let _overviewSummary = null;
let _filterOptions = { kbli_codes: [], aktivitas_codes: [] };
let _sortKeyUi = "date";

const _tableFilterState = {
  search: "",
  date_from: "",
  date_to: "",
  kbli_code: "",
  aktivitas_code: "",
};

const _tablePaginationState = {
  page: 1,
  per_page: PER_PAGE,
  total_items: 0,
  total_pages: 1,
  has_prev: false,
  has_next: false,
};

const VIEW_META = {
  overview: {
    title: "KABARE Dashboard",
    subtitle: "Pemantauan fenomena ekonomi berbasis berita lokal",
  },
  data: {
    title: "Data Berita",
    subtitle: "Tabel berita, filter, dan ekspor data",
  },
  insight: {
    title: "Insight AI",
    subtitle: "Analisis otomatis indikator ekonomi, kemiskinan, dan pengangguran",
  },
  chat: {
    title: "AI Chat",
    subtitle: "Diskusi interaktif berbasis berita tersitasi",
  },
  scrape: {
    title: "Scraping Manual",
    subtitle: "Kontrol scraping manual untuk kebutuhan operasional admin",
  },
};

const BULAN_ID = {
  januari: 0,
  februari: 1,
  maret: 2,
  april: 3,
  mei: 4,
  juni: 5,
  juli: 6,
  agustus: 7,
  september: 8,
  oktober: 9,
  november: 10,
  desember: 11,
};

// ── KBLI: Mapping kode → deskripsi (sinkron dengan KBLI_KEY_MAPPING di core/kbli_utils.py) ──
// KBLI 2025: 22 kategori standar (A–V) + 2 kategori custom (KE, PG)
const KBLI_KEY_MAPPING = {
  A:  "Pertanian, Kehutanan, dan Perikanan",
  B:  "Pertambangan dan Penggalian",
  C:  "Industri",
  D:  "Penyediaan Listrik, Gas, Uap/Air Panas, dan Udara Dingin",
  E:  "Penyediaan Air; Pengelolaan Air Limbah, Penanganan Limbah, dan Remediasi",
  F:  "Konstruksi",
  G:  "Perdagangan Besar dan Eceran",
  H:  "Transportasi dan Penyimpanan",
  I:  "Aktivitas Penyediaan Akomodasi dan Makan Minum",
  J:  "Aktivitas Penerbitan, Penyiaran, serta Produksi dan Distribusi Konten",
  K:  "Aktivitas Telekomunikasi, Pemrograman Komputer, Konsultansi, dan Jasa Informasi",
  L:  "Aktivitas Keuangan dan Asuransi",
  M:  "Aktivitas Real Estat",
  N:  "Aktivitas Profesional, Ilmiah, dan Teknis",
  O:  "Aktivitas Administratif dan Penunjang Usaha",
  P:  "Administrasi Pemerintahan dan Pertahanan, Serta Jaminan Sosial Wajib",
  Q:  "Pendidikan",
  R:  "Aktivitas Kesehatan Manusia dan Aktivitas Sosial",
  S:  "Kesenian, Olahraga, dan Rekreasi",
  T:  "Aktivitas Jasa Lainnya",
  U:  "Aktivitas Rumah Tangga sebagai Pemberi Kerja",
  V:  "Aktivitas Badan Internasional dan Badan Ekstra Internasional Lainnya",
  KE: "Kemiskinan",
  PG: "Pengangguran",
};

// Helper: cek apakah nilai KBLI tidak relevan / tidak valid untuk chart/filter
// (Sistem baru berbasis LLM: tidak ada lagi format "confidence rendah")
function _isKbliIrrelevant(kbli) {
  if (!kbli) return true;
  const k = kbli.trim();
  return k === "—" || k.toLowerCase().startsWith("tidak relevan");
}

// ── Aktivitas Ekonomi: Mapping nomor → deskripsi (sinkron dengan AKTIVITAS_LABELS di core/aktivitas_utils.py) ──
const AKTIVITAS_LABELS = {
  1:  "Kondisi perekonomian di kabupaten/kota secara umum",
  2:  "Aktivitas panen hasil tanaman pangan (padi, jagung, palawija)",
  3:  "Aktivitas panen hasil tanaman lainnya (perkebunan, hortikultura)",
  4:  "Aktivitas rumah potong hewan (RPH)",
  5:  "Aktivitas penangkapan/budidaya ikan laut dan darat",
  6:  "Aktivitas pertambangan non migas (batubara, bijih logam, dll)",
  7:  "Aktivitas penggalian (pasir, kerikil)",
  8:  "Aktivitas produksi CPO",
  9:  "Aktivitas industri makanan dan minuman selain CPO",
  10: "Aktivitas penjualan/penyaluran migas (BBM & LPG)",
  11: "Aktivitas penjualan dan reparasi mobil dan sepeda motor",
  12: "Aktivitas pengiriman barang/ekspedisi",
  13: "Aktivitas/keramaian di terminal bis/travel/pool",
  14: "Aktivitas usaha perhotelan",
  15: "Jumlah pengunjung rumah sakit, klinik, dan laboratorium kesehatan",
  16: "Aktivitas/transaksi jual beli di pasar tradisional",
  17: "Aktivitas/transaksi jual beli di mall/pusat perbelanjaan modern terbesar",
  18: "Banyaknya penyewaan ruang untuk berjualan di mall/supermarket (tenant)",
  19: "Aktivitas/keramaian pengunjung restoran dan rumah makan",
  20: "Jumlah pengunjung tempat wisata komersial",
  21: "Aktivitas penyaluran dana bantuan penanggulangan bencana oleh LNPRT",
  22: "Aktivitas partai politik (kampanye, kongres, musda, dll)",
  23: "Aktivitas perayaan kegiatan keagamaan",
  24: "Aktivitas pembangunan/renovasi besar-besaran rumah/tempat tinggal",
  25: "Aktivitas pembangunan gedung dan infrastruktur (jalan, jembatan, dll)",
  26: "Aktivitas pemberian bansos dari pemerintah",
  27: "Aktivitas bongkar muat di pelabuhan/bandara/stasiun",
};

function buildMasterFilterOptions() {
  const kbli_codes = Object.keys(KBLI_KEY_MAPPING);
  const aktivitas_codes = Object.keys(AKTIVITAS_LABELS).sort(
    (a, b) => Number(a) - Number(b),
  );

  return { kbli_codes, aktivitas_codes };
}

// ── Filter tag tidak informatif (mirror logic dari core/utils.py clean_tags) ──

// 1. Kata lokasi — word-boundary: menangkap "berita tegal", "pemkab tegal", dll.
const _RE_LOCATION_WORD = /\b(?:tegal|kota tegal|kabupaten tegal|slawi|jawa tengah|jateng|brebes|pemalang|pekalongan|batang|kendal|pemkab|pemkot)\b/i;

// 2. Stop words — exact match (seluruh tag, lowercase)
const _STOPWORD_EXACT = new Set([
  "ini","itu","dan","di","ke","dari","yang","untuk",
  "dengan","ada","bisa","juga","sudah","akan","lagi",
  "oleh","atau","saja","pun","bila","jika","ia","si",
  "hari","bulan","tahun","orang","pada","hal","cara",
  "bagi","agar","saat","serta","lebih","belum","masih",
  "kami","kamu","anda","kita","mereka","dia","nya",
  "berita","terbaru","update",
]);

/**
 * Kembalikan true jika tag layak ditampilkan (bukan noise).
 * - Bukan angka atau ≤ 2 karakter
 * - Tidak mengandung kata lokasi sebagai kata utuh (\b...\b)
 * - Bukan stop word
 */
function _isCleanTag(raw) {
  const t = raw.trim().replace(/^#/, "");
  if (!t) return false;
  if (t.length <= 2) return false;                 // terlalu pendek
  if (/^\d+$/.test(t)) return false;               // murni angka
  if (_RE_LOCATION_WORD.test(t)) return false;     // mengandung kata lokasi
  if (_STOPWORD_EXACT.has(t.toLowerCase())) return false;  // stop word
  return true;
}

// Map KBLI kode → CSS group class untuk badge berwarna
const KBLI_GROUP_CLASS = {
  A1: "a",
  A2: "a",
  A3: "a",
  B1: "b",
  B2: "b",
  B3: "b",
  B4: "b",
  C1: "c",
  C2: "c",
  C3: "c",
  C4: "c",
  C5: "c",
  D: "d",
  E: "e",
  F: "f",
  G: "g",
  H1: "h",
  H2: "h",
  H3: "h",
  H4: "h",
  H5: "h",
  I: "i",
  J: "j",
  K: "k",
  L: "l",
  MN: "mn",
  O: "o",
  P: "p",
  Q: "q",
  RSTU: "rstu",
  KE: "ke",
  PG: "pg",
};

function parseDateID(str) {
  if (!str) return new Date(0);
  // Format: "23 Februari 2026, 16:04 WIB"
  const m = str.match(/(\d{1,2})\s+(\w+)\s+(\d{4}),?\s+(\d{2}):(\d{2})/);
  if (!m) return new Date(0);
  const [, day, bulan, year, hour, min] = m;
  const month = BULAN_ID[bulan.toLowerCase()];
  if (month === undefined) return new Date(0);
  return new Date(+year, month, +day, +hour, +min);
}

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
let chartInstance = null;
let clockTimer = null;
let pollTimer = null;
let refreshTimer = null; // auto-refresh untuk last scrape & data
let maxArticlesGlobal = 150;

// ── Last Scrape Time ──────────────────────────────────────────────────────────

async function loadLastScrape() {
  try {
    const res = await fetch("/api/last-scrape");
    if (!res.ok) return;
    const json = await res.json();

    // ── Format waktu scraping ─────────────────────────────────────────────
    let timeText = "belum pernah";
    if (json.status === "ok" && json.last_scrape) {
      const dt = new Date(json.last_scrape);
      timeText =
        dt.toLocaleString("id-ID", {
          day: "2-digit",
          month: "long",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          timeZone: "Asia/Jakarta",
        }) + " WIB";
    }

    // ── Format berita baru ────────────────────────────────────────────────
    const count =
      json.status === "ok" && json.new_count != null ? json.new_count : 0;
    const newText =
      count > 0
        ? `${count} berita baru hari ini`
        : "Belum ada berita baru hari ini";

    // ── Isi elemen admin (scrapeSection) ─────────────────────────────────
    const elAdmin = document.getElementById("lastScrapeTime");
    if (elAdmin) elAdmin.textContent = timeText;

    const badgeAdmin = document.getElementById("newArticlesBadge");
    const textAdmin = document.getElementById("newArticlesText");
    if (badgeAdmin && textAdmin) {
      textAdmin.textContent = newText;
      badgeAdmin.style.display = "";
    }

    // ── Isi elemen info bar (semua user) ──────────────────────────────────
    const elUser = document.getElementById("lastScrapeTimeUser");
    if (elUser) elUser.textContent = timeText;

    const badgeUser = document.getElementById("newArticlesBadgeUser");
    const textUser = document.getElementById("newArticlesTextUser");
    if (badgeUser && textUser) {
      textUser.textContent = newText;
      badgeUser.style.display = "";
    }
  } catch (e) {
    ["lastScrapeTime", "lastScrapeTimeUser"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.textContent = "—";
    });
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  if (typeof initAppShell === "function") {
    initAppShell();
  }
  startRealtimeClock();
  await loadUserInfo();
  initSidebarNavigation();
  initFloatingChat();
  _filterOptions = buildMasterFilterOptions();
  await loadOverviewSummary();
  await loadBerita();
  loadLastScrape();
  loadAIInsights();
  animateCards();
  startAutoRefresh();

  // ── Tooltip KBLI: delegasi event ke dokumen ───────────────────────────────
  document.addEventListener("mouseover", (e) => {
    const btn = e.target.closest(".kbli-info-btn");
    if (btn) _showKbliTooltip(btn);
  });
  document.addEventListener("mouseout", (e) => {
    const btn = e.target.closest(".kbli-info-btn");
    if (btn) _hideKbliTooltip();
  });
});

function startRealtimeClock() {
  updateTimestamp();
  if (clockTimer) clearInterval(clockTimer);
  clockTimer = setInterval(updateTimestamp, 1000);
}

// ── Auto-refresh (tiap 5 menit) ───────────────────────────────────────────────
// Biar last scrape & data tabel otomatis update kalau cron baru saja jalan.

const AUTO_REFRESH_MS = 5 * 60 * 1000; // 5 menit

function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(async () => {
    // Jangan refresh kalau sedang ada polling scraping manual
    if (pollTimer) return;
    await loadLastScrape();
    await loadOverviewSummary();
    await loadBerita();
  }, AUTO_REFRESH_MS);
}

async function loadOverviewSummary() {
  try {
    const res = await fetch("/api/dashboard/overview/summary");
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const json = await res.json();
    if (json.status !== "ok") return;
    _overviewSummary = json.data || null;
    updateSummary();
    renderChart();
    renderKbliChart();
  } catch (e) {
    console.error("Gagal memuat ringkasan overview:", e);
  }
}

function updateTimestamp() {
  const el = document.getElementById("headerTimestamp");
  const now = new Date();
  const tanggal = now.toLocaleDateString("id-ID", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "2-digit",
  });
  const waktu = now.toLocaleTimeString("id-ID", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  el.textContent = `${tanggal} • ${waktu}`;
}

// ── User info ─────────────────────────────────────────────────────────────────

async function loadUserInfo() {
  try {
    const res = await fetch("/api/me");
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const json = await res.json();
    if (json.status === "ok") {
      if (json.must_change_password) {
        window.location.href = "/change-password";
        return;
      }

      currentUser = json;
      const userEl = document.getElementById("headerUser");
      if (userEl) userEl.textContent = json.username;
      const adminUsersLink = document.getElementById("adminUsersLink");
      const guideUserCard = document.getElementById("guideUserCard");
      const guideAdminCard = document.getElementById("guideAdminCard");

      // Admin: sembunyikan info bar (sudah ada di scrape card)
      // Non-admin: sembunyikan scrape section
      if (json.role === "admin") {
        const infoBar = document.getElementById("scrapeInfoBar");
        if (infoBar) infoBar.style.display = "none";
        if (adminUsersLink) adminUsersLink.style.display = "inline-flex";
        if (guideAdminCard) guideAdminCard.style.display = "block";
        if (guideUserCard) guideUserCard.style.display = "none";
      } else {
        const scrapeSection = document.getElementById("scrapeSection");
        if (scrapeSection) scrapeSection.style.display = "none";
        if (adminUsersLink) adminUsersLink.style.display = "none";
        if (guideUserCard) guideUserCard.style.display = "block";
        if (guideAdminCard) guideAdminCard.style.display = "none";

        if (_activeView === "scrape") {
          _openView("overview", { updateHash: true });
        }
      }
    }
  } catch (e) {
    console.error("Gagal memuat info user:", e);
  }
}

function animateCards() {
  document.querySelectorAll(".card-animate").forEach((card, i) => {
    setTimeout(() => card.classList.add("visible"), 100 + i * 80);
  });
}

// ── Load berita dari API ──────────────────────────────────────────────────────
// Params opsional: { search, date_from, date_to } — dikirim ke backend
// sehingga response tidak membawa kolom `content` yang berat.

async function loadBerita({ search = "", date_from = "", date_to = "" } = {}) {
  try {
    if (search !== undefined) _tableFilterState.search = search.trim();
    if (date_from !== undefined) _tableFilterState.date_from = date_from;
    if (date_to !== undefined) _tableFilterState.date_to = date_to;

    const params = new URLSearchParams();
    if (_tableFilterState.search) params.set("search", _tableFilterState.search);
    if (_tableFilterState.date_from) params.set("date_from", _tableFilterState.date_from);
    if (_tableFilterState.date_to) params.set("date_to", _tableFilterState.date_to);
    if (_selectedKbli) params.set("kbli_code", _selectedKbli);
    if (_selectedAktivitas) params.set("aktivitas_code", _selectedAktivitas);

    params.set("page", String(currentPage));
    params.set("per_page", String(_tablePaginationState.per_page));
    params.set("sort_by", sortField);
    params.set("sort_dir", sortAsc ? "asc" : "desc");

    const url =
      "/api/berita" + (params.toString() ? "?" + params.toString() : "");
    const res = await fetch(url);
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const json = await res.json();
    if (json.status === "ok") {
      filteredData = json.data || [];
      const pg = json.pagination || {};
      _tablePaginationState.page = Number(pg.page || currentPage || 1);
      _tablePaginationState.per_page = Number(pg.per_page || PER_PAGE);
      _tablePaginationState.total_items = Number(pg.total_items || 0);
      _tablePaginationState.total_pages = Number(pg.total_pages || 1);
      _tablePaginationState.has_prev = Boolean(pg.has_prev);
      _tablePaginationState.has_next = Boolean(pg.has_next);

      currentPage = _tablePaginationState.page;

      renderTable();
    }
  } catch (err) {
    console.error("Gagal memuat berita:", err);
  }
}

// ── Scrape: trigger ───────────────────────────────────────────────────────────

async function scrapeBerita() {
  const btn = document.getElementById("btnScrape");
  btn.classList.add("loading");
  btn.disabled = true;

  const input = document.getElementById("maxArticles");
  maxArticlesGlobal = input.value ? parseInt(input.value) : 150;

  showProgress();
  resetProgressBars();

  try {
    const res = await fetch("/api/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_articles: maxArticlesGlobal }),
    });

    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }

    const json = await res.json();

    if (json.status === "started") {
      startPolling();
    } else {
      alert("Error: " + (json.message || "Terjadi kesalahan."));
      hideProgress();
      btn.classList.remove("loading");
      btn.disabled = false;
    }
  } catch (err) {
    alert("Gagal menjalankan scraping: " + err.message);
    hideProgress();
    btn.classList.remove("loading");
    btn.disabled = false;
  }
}

// ── Progress polling ──────────────────────────────────────────────────────────

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(fetchProgress, 1500);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function fetchProgress() {
  try {
    const res = await fetch("/api/scrape/progress");
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const json = await res.json();
    updateProgressUI(json.progress, json.overall);

    if (json.overall && json.overall.done) {
      stopPolling();
      onScrapingDone(json.overall);
    }
  } catch (err) {
    console.error("Gagal fetch progress:", err);
  }
}

const SOURCE_KEYS = [
  "radartegal",
  "panturapost",
  "tribunjateng",
  "kompas",
  "setdategal",
];

function resetProgressBars() {
  document.getElementById("progressSubtitle").textContent = "Memulai...";
  SOURCE_KEYS.forEach((key) => {
    document.getElementById(`bar-${key}`).style.width = "0%";
    document.getElementById(`bar-${key}`).className = "progress-bar-fill";
    document.getElementById(`count-${key}`).textContent = "0";
    document.getElementById(`status-${key}`).textContent = "Menunggu...";
  });
}

function updateProgressUI(progress, overall) {
  const max = maxArticlesGlobal || 150;
  let runningSource = "";

  SOURCE_KEYS.forEach((key) => {
    const src = progress[key];
    if (!src) return;

    const pct = Math.min(100, Math.round((src.scraped / max) * 100));
    const bar = document.getElementById(`bar-${key}`);
    const count = document.getElementById(`count-${key}`);
    const status = document.getElementById(`status-${key}`);

    bar.style.width = pct + "%";
    count.textContent = src.scraped;

    if (src.status === "running") {
      bar.className = "progress-bar-fill running";
      status.textContent = src.message || "Berjalan...";
      runningSource = key;
    } else if (src.status === "done") {
      bar.className = "progress-bar-fill done";
      bar.style.width = "100%";
      status.textContent = src.message || "Selesai";
    } else if (src.status === "error") {
      bar.className = "progress-bar-fill error";
      status.textContent = src.message || "Error";
    } else {
      status.textContent = src.message || "Menunggu...";
    }
  });

  const subtitle = document.getElementById("progressSubtitle");
  if (runningSource) {
    const labels = {
      radartegal: "Radar Tegal",
      panturapost: "Pantura Post",
      tribunjateng: "Tribun Jateng",
      kompas: "Kompas",
      setdategal: "Setda Tegal",
    };
    subtitle.textContent = `Sedang: ${labels[runningSource] || runningSource}`;
  } else if (overall && overall.active) {
    subtitle.textContent = "Menyiapkan sumber berikutnya...";
  }
}

function onScrapingDone(overall) {
  const btn = document.getElementById("btnScrape");
  btn.classList.remove("loading");
  btn.disabled = false;

  const subtitle = document.getElementById("progressSubtitle");
  const total = overall.total_inserted || 0;
  subtitle.textContent = `Selesai — ${total} berita baru disimpan`;

  SOURCE_KEYS.forEach((key) => {
    const bar = document.getElementById(`bar-${key}`);
    if (bar.className.includes("running")) {
      bar.className = "progress-bar-fill done";
      bar.style.width = "100%";
    }
  });

  if (overall.error) {
    alert("Scraping selesai dengan error: " + overall.error);
  }

  loadOverviewSummary();
  loadBerita();
  loadLastScrape();
}

function showProgress() {
  document.getElementById("scrapeProgress").style.display = "block";
}

function hideProgress() {
  document.getElementById("scrapeProgress").style.display = "none";
}

// ── Summary cards ─────────────────────────────────────────────────────────────

function updateSummary() {
  const data = _overviewSummary || {};

  // Card 1: Total Berita (30 hari)
  document.getElementById("totalBerita").textContent = String(data.total_30d || 0);

  // Card 2: KBLI Terbanyak (30 hari)
  const kbliSorted = (data.top_kbli || []).map((item) => [item.code, item.count]);
  const topKbliEl  = document.getElementById("topKbli");
  if (kbliSorted.length > 0) {
    const topKode = String(kbliSorted[0][0] || "");
    const topDesc = KBLI_KEY_MAPPING[topKode];
    const label   = topDesc
      ? `${topKode} — ${topDesc.length > 20 ? topDesc.slice(0, 18) + "…" : topDesc}`
      : topKode;
    if (topKbliEl) {
      topKbliEl.textContent = label;
      topKbliEl.classList.add("text-value");
    }
  } else {
    if (topKbliEl) topKbliEl.textContent = "—";
  }

  // Card 3: Tag Terbanyak (30 hari)
  const tagSorted = data.top_tags_30d || [];
  const topEl     = document.getElementById("topTag");
  if (tagSorted.length > 0) {
    topEl.textContent = tagSorted[0].tag || "—";
    topEl.classList.add("text-value");
  } else {
    topEl.textContent = "—";
  }

  // Card 4: Berita Terbaru (tanggal artikel terbaru dari semua data)
  const latestEl = document.getElementById("tanggalTerbaru");
  latestEl.textContent = data.latest_date || "—";
}

// ── Chart ─────────────────────────────────────────────────────────────────────

const BULAN_NAMA_ID = [
  "Januari",
  "Februari",
  "Maret",
  "April",
  "Mei",
  "Juni",
  "Juli",
  "Agustus",
  "September",
  "Oktober",
  "November",
  "Desember",
];

function renderChart() {
  const now = new Date();
  const thisYear = now.getFullYear();
  const thisMonth = now.getMonth();

  const sorted = (_overviewSummary?.top_tags_month || [])
    .map((item) => [item.tag, item.count]);
  const fullLabels = sorted.map((e) => e[0]);
  const values = sorted.map((e) => e[1]);

  // Truncate label panjang
  const MAX_LABEL = 26;
  const displayLabels = fullLabels.map((l) =>
    l.length > MAX_LABEL ? l.slice(0, MAX_LABEL) + "…" : l,
  );

  // Update label bulan di header
  const monthEl = document.getElementById("chartMonthLabel");
  if (monthEl) monthEl.textContent = `${BULAN_NAMA_ID[thisMonth]} ${thisYear}`;

  const canvas = document.getElementById("chartTags");
  if (!canvas) return;
  if (chartInstance) chartInstance.destroy();

  if (sorted.length === 0) {
    // Tidak ada data bulan ini — tampilkan pesan kosong
    if (chartInstance) {
      chartInstance.destroy();
      chartInstance = null;
    }
    canvas.style.display = "none";
    let empty = document.getElementById("chartEmpty");
    if (!empty) {
      empty = document.createElement("p");
      empty.id = "chartEmpty";
      empty.style.cssText =
        "text-align:center;color:#aaa;padding:32px 0;font-size:14px;";
      canvas.parentNode.appendChild(empty);
    }
    empty.textContent = `Belum ada berita bulan ${BULAN_NAMA_ID[thisMonth]} ${thisYear}.`;
    return;
  }

  // Sembunyikan pesan kosong kalau ada
  canvas.style.display = "";
  const empty = document.getElementById("chartEmpty");
  if (empty) empty.remove();

  chartInstance = new Chart(canvas, {
    type: "bar",
    data: {
      labels: displayLabels,
      datasets: [
        {
          label: "Jumlah Berita",
          data: values,
          backgroundColor: [
            "rgba(232,112,10,0.90)",
            "rgba(232,112,10,0.76)",
            "rgba(232,112,10,0.62)",
            "rgba(232,112,10,0.50)",
            "rgba(232,112,10,0.38)",
          ],
          borderColor: "transparent",
          borderWidth: 0,
          borderRadius: 6,
          borderSkipped: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: "y",
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => fullLabels[items[0].dataIndex],
            label: (item) => `  ${item.raw} berita`,
          },
          padding: 10,
          bodyFont: { size: 13 },
          titleFont: { size: 13, weight: "bold" },
        },
      },
      scales: {
        x: {
          beginAtZero: true,
          ticks: { precision: 0, font: { size: 12 }, color: "#888" },
          grid: { color: "rgba(0,0,0,0.05)" },
          border: { display: false },
        },
        y: {
          ticks: {
            font: { size: 14, weight: "600" },
            color: "#222",
            crossAlign: "far",
          },
          grid: { display: false },
          border: { display: false },
        },
      },
      layout: { padding: { right: 20, top: 4, bottom: 4 } },
      barThickness: 15,
      maxBarThickness: 32,
    },
  });
}

// ── KBLI Chart (Top 5, 30 hari terakhir) ──────────────────────────────────────

let kbliChartInstance = null;

function renderKbliChart() {
  const sorted = (_overviewSummary?.top_kbli || [])
    .map((item) => [item.code, item.count]);

  const canvas = document.getElementById("chartKbli");
  if (!canvas) return;
  if (kbliChartInstance) { kbliChartInstance.destroy(); kbliChartInstance = null; }

  if (sorted.length === 0) {
    canvas.style.display = "none";
    let empty = document.getElementById("kbliChartEmpty");
    if (!empty) {
      empty = document.createElement("p");
      empty.id = "kbliChartEmpty";
      empty.style.cssText = "text-align:center;color:#aaa;padding:32px 0;font-size:14px;";
      canvas.parentNode.appendChild(empty);
    }
    empty.textContent = "Belum ada data KBLI dalam 30 hari terakhir.";
    return;
  }

  canvas.style.display = "";
  const emptyEl = document.getElementById("kbliChartEmpty");
  if (emptyEl) emptyEl.remove();

  // Label: "KODE — Deskripsi singkat"
  const fullLabels    = sorted.map(([kode]) => {
    const desc = KBLI_KEY_MAPPING[kode];
    return desc ? `${kode} — ${desc}` : kode;
  });
  const MAX_LABEL     = 28;
  const displayLabels = fullLabels.map((l) =>
    l.length > MAX_LABEL ? l.slice(0, MAX_LABEL) + "…" : l,
  );
  const values = sorted.map(([, v]) => v);

  // Palet oranye — konsisten dengan tema aplikasi
  const BG_COLORS = [
    "rgba(232,112,10,0.90)",
    "rgba(232,112,10,0.76)",
    "rgba(232,112,10,0.62)",
    "rgba(232,112,10,0.50)",
    "rgba(232,112,10,0.38)",
  ];

  kbliChartInstance = new Chart(canvas, {
    type: "bar",
    data: {
      labels: displayLabels,
      datasets: [{
        label: "Jumlah Berita",
        data: values,
        backgroundColor: BG_COLORS.slice(0, sorted.length),
        borderColor: "transparent",
        borderWidth: 0,
        borderRadius: 6,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: "y",
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => fullLabels[items[0].dataIndex],
            label: (item)  => `  ${item.raw} berita`,
          },
          padding: 10,
          bodyFont:  { size: 13 },
          titleFont: { size: 13, weight: "bold" },
        },
      },
      scales: {
        x: {
          beginAtZero: true,
          ticks: { precision: 0, font: { size: 12 }, color: "#888" },
          grid:  { color: "rgba(0,0,0,0.05)" },
          border: { display: false },
        },
        y: {
          ticks: {
            font: { size: 13, weight: "600" },
            color: "#222",
            crossAlign: "far",
          },
          grid:   { display: false },
          border: { display: false },
        },
      },
      layout: { padding: { right: 20, top: 4, bottom: 4 } },
      barThickness: 15,
      maxBarThickness: 32,
    },
  });
}

// ── Table render ──────────────────────────────────────────────────────────────

function renderTable() {
  const tbody = document.getElementById("tableBody");
  const pageData = filteredData;

  if (pageData.length === 0) {
    tbody.innerHTML = `
            <tr class="empty-row"><td colspan="7">
                <div class="empty-state">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#ccc"
                        stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                    </svg>
                    <p>Belum ada data. Klik <strong>"Scrape Berita"</strong> untuk memulai.</p>
                </div>
            </td></tr>`;
    document.getElementById("pagination").innerHTML = "";
    return;
  }

  tbody.innerHTML = pageData
    .map((item, i) => {
      const no = (currentPage - 1) * _tablePaginationState.per_page + i + 1;
      const tags = parseTags(item.tags)
        .map((t) => `<span class="tag-chip">#${escapeHtml(t)}</span>`)
        .join(" ");
      const source = escapeHtml(item.source || "—");
      const date = escapeHtml(item.date || "—");
      const kbli = renderKbliCell(item.kbli || "", item.aktivitas_ekonomi || "");
      const internalLink = item.id ? `/berita/${item.id}` : "#";
      const externalLink = escapeHtml(item.url || "#");
      return `
        <tr>
            <td class="td-no">${no}</td>
            <td class="td-judul">${escapeHtml(item.title || "")}</td>
            <td class="td-source">${source}</td>
            <td class="td-date">${date}</td>
            <td class="td-tags">${tags || "—"}</td>
            <td class="td-kbli">${kbli}</td>
            <td class="td-link">
                <div class="td-link-inner">
                    <a href="${internalLink}" class="link-btn">Buka</a>
                    <a href="${externalLink}" target="_blank" rel="noopener noreferrer" class="link-ext" title="Buka sumber asli">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
                        </svg>
                    </a>
                </div>
            </td>
        </tr>`;
    })
    .join("");

  renderPagination();
}

function parseTags(raw) {
  if (!raw) return [];
  return raw
    .split(/\s*\|\s*|,\s*/)
    .map((t) => t.trim().replace(/^#/, ""))
    .filter(Boolean);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function _normalizeCitationMarkers(text, prefixes = "S") {
  let normalized = String(text || "");
  const safePrefixes = String(prefixes || "S").replace(/[^A-Z]/gi, "") || "S";
  const cls = `[${safePrefixes}]`;

  // Step 0: Expand bracket berkoma: [P19, P22] → [P19][P22]
  //         atau mixed: [P02, 3, P13] → [P02][P03][P13]
  const commaBracketRe = new RegExp(
    `\\[([${safePrefixes}]\\d{1,2}(?:\\s*,\\s*[${safePrefixes}]?\\d{1,2})+)\\]`,
    "gi"
  );
  normalized = normalized.replace(commaBracketRe, (_, inner) => {
    const tokens = inner.split(",").map((t) => t.trim()).filter(Boolean);
    // Prefix default: ambil dari token pertama yang ada huruf awalan
    let defaultPrefix = safePrefixes[0];
    for (const tok of tokens) {
      const m = tok.match(new RegExp(`^([${safePrefixes}])`, "i"));
      if (m) { defaultPrefix = m[1].toUpperCase(); break; }
    }
    return tokens.map((tok) => {
      const mFull = tok.match(new RegExp(`^([${safePrefixes}])(\\d{1,2})$`, "i"));
      const mNum  = tok.match(/^(\d{1,2})$/);
      if (mFull) return `[${mFull[1].toUpperCase()}${String(parseInt(mFull[2], 10)).padStart(2, "0")}]`;
      if (mNum)  return `[${defaultPrefix}${String(parseInt(mNum[1], 10)).padStart(2, "0")}]`;
      return "";
    }).join("");
  });

  // Step 1: Expand marker tergabung: S01S03S04 → [S01][S03][S04]
  const concatRe = new RegExp(`(?:${cls}\\d{2}){2,}`, "gi");
  normalized = normalized.replace(concatRe, (token) => {
    const parts = token.toUpperCase().match(new RegExp(`${cls}\\d{2}`, "g")) || [];
    return parts.map((p) => `[${p}]`).join("");
  });

  // Step 2: Bungkus marker bare: S01 → [S01] (jika belum dibungkus)
  const singleRe = new RegExp(`(?<!\\[)\\b(${cls}\\d{2})\\b(?!\\])`, "gi");
  normalized = normalized.replace(singleRe, "[$1]");
  return normalized;
}

function _markdownToHtmlSafe(markdownText) {
  const escaped = escapeHtml(markdownText || "");
  if (window.marked && typeof window.marked.parse === "function") {
    return window.marked.parse(escaped, {
      gfm: true,
      breaks: true,
      headerIds: false,
      mangle: false,
    });
  }
  return escaped.replace(/\n/g, "<br>");
}

// ── KBLI: Render sel tabel + floating tooltip ─────────────────────────────────

/**
 * Kembalikan CSS group class untuk kode KBLI.
 */
function _kbliGroupClass(kode) {
  const g = KBLI_GROUP_CLASS[kode.toUpperCase()];
  return g ? `kbli-g-${g}` : "kbli-g-rstu";
}

/**
 * Render konten sel KBLI.
 * Format nilai dari DB (sistem LLM baru):
 * - "KODE/Deskripsi"  → badge berwarna dengan kode & deskripsi
 * - "Tidak Relevan"   → badge abu-abu
 * - "—"              → dash (artikel tanpa konten)
 */
function renderKbliCell(kbliStr, aktivitasStr) {
  // Render badge KBLI
  let kbliHtml;
  if (!kbliStr || !kbliStr.trim()) {
    kbliHtml = "—";
  } else if (_isKbliIrrelevant(kbliStr)) {
    const label = kbliStr.trim() === "—" ? "—" : "Tidak Relevan";
    kbliHtml = `<span class="kbli-tidak-relevan">${label}</span>`;
  } else {
    const slashIdx = kbliStr.indexOf("/");
    if (slashIdx !== -1) {
      const kode = kbliStr.slice(0, slashIdx).trim().toUpperCase();
      const desc = kbliStr.slice(slashIdx + 1).trim();
      const groupCls = _kbliGroupClass(kode);
      kbliHtml = (
        `<span class="kbli-badge ${groupCls}">` +
        `<span class="kbli-badge-letter">${escapeHtml(kode)}</span>` +
        `<span class="kbli-badge-text">${escapeHtml(desc)}</span>` +
        `</span>`
      );
    } else {
      const kode = kbliStr.trim().toUpperCase();
      const groupCls = _kbliGroupClass(kode);
      kbliHtml = (
        `<span class="kbli-badge ${groupCls}">` +
        `<span class="kbli-badge-letter">${escapeHtml(kode)}</span>` +
        `<span class="kbli-badge-text">${escapeHtml(kode)}</span>` +
        `</span>`
      );
    }
  }

  // Render badge Aktivitas Ekonomi (nomor lingkaran + label penuh, mirip KBLI badge)
  let aktivitasHtml = "";
  if (aktivitasStr && aktivitasStr.trim() && aktivitasStr.trim() !== "—") {
    const slashIdx = aktivitasStr.indexOf("/");
    const numStr   = slashIdx !== -1 ? aktivitasStr.slice(0, slashIdx).trim() : "";
    const fullLabel = slashIdx !== -1
      ? aktivitasStr.slice(slashIdx + 1).trim()
      : aktivitasStr.trim();
    if (fullLabel) {
      const numDisplay = numStr || "·";
      aktivitasHtml = (
        `<span class="aktivitas-badge">` +
        `<span class="aktivitas-badge-num">${escapeHtml(numDisplay)}</span>` +
        `<span class="aktivitas-badge-text">${escapeHtml(fullLabel)}</span>` +
        `</span>`
      );
    }
  }

  return kbliHtml + aktivitasHtml;
}

// Elemen tooltip floating (satu, di-append ke body saat pertama dipakai)
let _kbliTooltipEl = null;
let _kbliTooltipArrow = null;

function _ensureKbliTooltip() {
  if (!_kbliTooltipEl) {
    _kbliTooltipEl = document.createElement("div");
    _kbliTooltipEl.className = "kbli-tooltip-floating";
    _kbliTooltipArrow = document.createElement("span");
    _kbliTooltipArrow.className = "kbli-tooltip-arrow";
    _kbliTooltipEl.appendChild(_kbliTooltipArrow);
    document.body.appendChild(_kbliTooltipEl);
  }
  return _kbliTooltipEl;
}

function _showKbliTooltip(btn) {
  const text = btn.dataset.kbliTooltip || "";
  const tooltip = _ensureKbliTooltip();

  // Isi teks (bersihkan node teks lama, biarkan arrow)
  Array.from(_kbliTooltipEl.childNodes).forEach((n) => {
    if (n !== _kbliTooltipArrow) _kbliTooltipEl.removeChild(n);
  });
  _kbliTooltipEl.insertBefore(document.createTextNode(text), _kbliTooltipArrow);

  tooltip.style.display = "block";
  tooltip.style.visibility = "hidden";

  // Posisi: hitung setelah layout
  requestAnimationFrame(() => {
    const bRect = btn.getBoundingClientRect();
    const tRect = tooltip.getBoundingClientRect();
    const scrollY = window.scrollY || window.pageYOffset;
    const scrollX = window.scrollX || window.pageXOffset;

    let top = bRect.top + scrollY - tRect.height - 10;
    let left = bRect.left + scrollX + bRect.width / 2 - tRect.width / 2;

    // Klem agar tidak melewati tepi viewport
    const vw = window.innerWidth;
    if (left < 8) left = 8;
    if (left + tRect.width > vw - 8) left = vw - 8 - tRect.width;

    // Posisi arrow relatif terhadap tooltip
    const arrowCenter = bRect.left + scrollX + bRect.width / 2 - left;
    _kbliTooltipArrow.style.left =
      Math.max(10, Math.min(tRect.width - 10, arrowCenter)) + "px";

    tooltip.style.top = top + "px";
    tooltip.style.left = left + "px";
    tooltip.style.visibility = "visible";
  });
}

function _hideKbliTooltip() {
  if (_kbliTooltipEl) _kbliTooltipEl.style.display = "none";
}

// ── Pagination ────────────────────────────────────────────────────────────────

function renderPagination() {
  const container = document.getElementById("pagination");
  const totalPages = _tablePaginationState.total_pages || 1;

  if (totalPages <= 1) {
    container.innerHTML = "";
    return;
  }

  let html = `<button class="page-btn" ${currentPage === 1 ? "disabled" : ""} onclick="goPage(${currentPage - 1})">‹</button>`;

  const range = getPageRange(currentPage, totalPages, 5);
  if (range[0] > 1) {
    html += `<button class="page-btn" onclick="goPage(1)">1</button>`;
    if (range[0] > 2) html += `<span class="page-info">…</span>`;
  }
  for (const p of range) {
    html += `<button class="page-btn ${p === currentPage ? "active" : ""}" onclick="goPage(${p})">${p}</button>`;
  }
  if (range[range.length - 1] < totalPages) {
    if (range[range.length - 1] < totalPages - 1)
      html += `<span class="page-info">…</span>`;
    html += `<button class="page-btn" onclick="goPage(${totalPages})">${totalPages}</button>`;
  }
  html += `<button class="page-btn" ${currentPage === totalPages ? "disabled" : ""} onclick="goPage(${currentPage + 1})">›</button>`;
  html += `<span class="page-info">${_tablePaginationState.total_items} berita</span>`;

  container.innerHTML = html;
}

function getPageRange(current, total, maxVisible) {
  let start = Math.max(1, current - Math.floor(maxVisible / 2));
  let end = start + maxVisible - 1;
  if (end > total) {
    end = total;
    start = Math.max(1, end - maxVisible + 1);
  }
  const range = [];
  for (let i = start; i <= end; i++) range.push(i);
  return range;
}

function goPage(p) {
  const totalPages = _tablePaginationState.total_pages || 1;
  if (p < 1 || p > totalPages) return;
  currentPage = p;
  loadBerita();
  document
    .getElementById("tableSection")
    .scrollIntoView({ behavior: "smooth", block: "start" });
}

// ── KBLI Filter ────────────────────────────────────────────────────────────────

let _selectedKbli = ""; // kode KBLI terpilih (kosong = semua)
let _selectedAktivitas = ""; // nomor aktivitas terpilih sebagai string (kosong = semua)

/**
 * Isi dropdown filter KBLI dari data yang ada.
 * Dipanggil setelah loadBerita() selesai.
 */
function populateKbliFilter() {
  const menu = document.getElementById("kbliFilterMenu");
  if (!menu) return;

  const kodeArr = _filterOptions.kbli_codes || [];

  if (kodeArr.length === 0) {
    menu.innerHTML = `<div style="padding:10px 14px;font-size:0.8rem;color:var(--text-muted)">Belum ada kategori KBLI</div>`;
    return;
  }

  let html = `<button class="kbli-filter-clear" onclick="clearKbliFilter()">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        Tampilkan Semua
    </button>
    <div class="kbli-filter-sep"></div>`;

  kodeArr.forEach((kode) => {
    const desc     = KBLI_KEY_MAPPING[kode] || kode;
    // Warna solid badge per group — sinkron dengan .kbli-g-X .kbli-badge-letter di CSS
    const _KBLI_BADGE_BG = {
      a: "#059669", b: "#ca8a04", c: "#4f46e5", d: "#f59e0b",
      e: "#0f9488", f: "#ea580c", g: "#dc2626", h: "#2563eb",
      i: "#c026d3", j: "#7c3aed", k: "#16a34a", l: "#475569",
      mn: "#e11d48", o: "#0369a1", p: "#65a30d", q: "#e63950",
      rstu: "#6b7280", ke: "#b91c1c", pg: "#c2410c",
    };
    const grp      = KBLI_GROUP_CLASS[kode] || "rstu";
    const badgeBg  = _KBLI_BADGE_BG[grp] || "#6b7280";
    const selectedCls = _selectedKbli === kode ? " selected" : "";
    html += `<button class="kbli-filter-option${selectedCls}" onclick="selectKbliFilter('${kode}')">
            <span class="kbli-filter-opt-letter" style="background:${badgeBg};">${escapeHtml(kode)}</span>
            <span>${escapeHtml(desc)}</span>
        </button>`;
  });

  menu.innerHTML = html;
}

function toggleKbliFilter() {
  const menu = document.getElementById("kbliFilterMenu");
  const btn = document.getElementById("kbliFilterBtn");
  if (!menu || !btn) return;
  const isOpen = menu.classList.contains("open");
  if (isOpen) {
    menu.classList.remove("open");
    btn.classList.remove("open");
  } else {
    populateKbliFilter();
    menu.classList.add("open");
    btn.classList.add("open");
  }
}

function selectKbliFilter(kode) {
  _selectedKbli = kode;
  _tableFilterState.kbli_code = kode;
  const btn = document.getElementById("kbliFilterBtn");
  const dot = document.getElementById("kbliFilterDot");
  const label = document.getElementById("kbliFilterLabel");
  if (label) label.textContent = kode;
  if (dot) dot.style.display = "";
  if (btn) btn.classList.add("active");
  // Tutup menu
  const menu = document.getElementById("kbliFilterMenu");
  if (menu) {
    menu.classList.remove("open");
    btn?.classList.remove("open");
  }
  currentPage = 1;
  applyFilters();
}

function clearKbliFilter() {
  _selectedKbli = "";
  _tableFilterState.kbli_code = "";
  const btn = document.getElementById("kbliFilterBtn");
  const dot = document.getElementById("kbliFilterDot");
  const label = document.getElementById("kbliFilterLabel");
  if (label) label.textContent = "Filter KBLI";
  if (dot) dot.style.display = "none";
  if (btn) btn.classList.remove("active");
  const menu = document.getElementById("kbliFilterMenu");
  if (menu) {
    menu.classList.remove("open");
    btn?.classList.remove("open");
  }
  currentPage = 1;
  applyFilters();
}

// Tutup menu KBLI jika klik di luar
document.addEventListener("click", (e) => {
  const wrapper = document.getElementById("kbliFilterWrapper");
  if (wrapper && !wrapper.contains(e.target)) {
    const menu = document.getElementById("kbliFilterMenu");
    const btn = document.getElementById("kbliFilterBtn");
    if (menu) menu.classList.remove("open");
    if (btn) btn.classList.remove("open");
  }
});

// ── Aktivitas Ekonomi Filter ──────────────────────────────────────────────────

/**
 * Isi dropdown filter Aktivitas Ekonomi dari data yang ada.
 * Dipanggil saat dropdown dibuka.
 */
function populateAktivitasFilter() {
  const menu = document.getElementById("aktivitasFilterMenu");
  if (!menu) return;

  const numArr = _filterOptions.aktivitas_codes || [];

  if (numArr.length === 0) {
    menu.innerHTML = `<div style="padding:10px 14px;font-size:0.8rem;color:var(--text-muted)">Belum ada data aktivitas</div>`;
    return;
  }

  let html = `<button class="kbli-filter-clear" onclick="clearAktivitasFilter()">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        Tampilkan Semua
    </button>
    <div class="kbli-filter-sep"></div>`;

  numArr.forEach((num) => {
    const desc = AKTIVITAS_LABELS[Number(num)] || `Aktivitas ${num}`;
    const selectedCls = _selectedAktivitas === num ? " selected" : "";
    html += `<button class="kbli-filter-option${selectedCls}" onclick="selectAktivitasFilter('${num}')">
            <span class="aktivitas-filter-num">${escapeHtml(num)}</span>
            <span>${escapeHtml(desc)}</span>
        </button>`;
  });

  menu.innerHTML = html;
}

function toggleAktivitasDropdown() {
  const menu = document.getElementById("aktivitasFilterMenu");
  const btn  = document.getElementById("aktivitasFilterBtn");
  if (!menu || !btn) return;
  const isOpen = menu.classList.contains("open");
  if (isOpen) {
    menu.classList.remove("open");
    btn.classList.remove("open");
  } else {
    populateAktivitasFilter();
    menu.classList.add("open");
    btn.classList.add("open");
  }
}

function selectAktivitasFilter(num) {
  _selectedAktivitas = num;
  _tableFilterState.aktivitas_code = num;
  const btn   = document.getElementById("aktivitasFilterBtn");
  const dot   = document.getElementById("aktivitasFilterDot");
  const label = document.getElementById("aktivitasFilterLabel");
  if (label) label.textContent = `Aktivitas ${num}`;
  if (dot)   dot.style.display = "";
  if (btn)   btn.classList.add("active");
  const menu = document.getElementById("aktivitasFilterMenu");
  if (menu) {
    menu.classList.remove("open");
    btn?.classList.remove("open");
  }
  currentPage = 1;
  applyFilters();
}

function clearAktivitasFilter() {
  _selectedAktivitas = "";
  _tableFilterState.aktivitas_code = "";
  const btn   = document.getElementById("aktivitasFilterBtn");
  const dot   = document.getElementById("aktivitasFilterDot");
  const label = document.getElementById("aktivitasFilterLabel");
  if (label) label.textContent = "Filter Aktivitas";
  if (dot)   dot.style.display = "none";
  if (btn)   btn.classList.remove("active");
  const menu = document.getElementById("aktivitasFilterMenu");
  if (menu) {
    menu.classList.remove("open");
    btn?.classList.remove("open");
  }
  currentPage = 1;
  applyFilters();
}

// Tutup menu Aktivitas jika klik di luar
document.addEventListener("click", (e) => {
  const wrapper = document.getElementById("aktivitasFilterWrapper");
  if (wrapper && !wrapper.contains(e.target)) {
    const menu = document.getElementById("aktivitasFilterMenu");
    const btn  = document.getElementById("aktivitasFilterBtn");
    if (menu) menu.classList.remove("open");
    if (btn)  btn.classList.remove("open");
  }
});

// ── Search & Date Filter ──────────────────────────────────────────────────────

/**
 * Konversi tanggal format Indonesia ("23 Februari 2026, 16:04 WIB") ke ISO string
 * untuk perbandingan dengan date input (yyyy-mm-dd).
 */
function parseDateToISO(str) {
  if (!str) return null;
  const d = parseDateID(str);
  if (!d || d.getTime() === 0) return null;
  // Format: yyyy-mm-dd
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

// Debounce helper — tunda panggilan applyFilters agar tidak spam API
let _filterDebounce = null;
function debounceFilters() {
  if (_filterDebounce) clearTimeout(_filterDebounce);
  _filterDebounce = setTimeout(applyFilters, 350);
}

function applyFilters() {
  const search = (document.getElementById("searchInput").value || "").trim();
  const date_from = document.getElementById("dateFrom").value; // "yyyy-mm-dd" or ""
  const date_to = document.getElementById("dateTo").value;

  _tableFilterState.search = search;
  _tableFilterState.date_from = date_from;
  _tableFilterState.date_to = date_to;
  _tableFilterState.kbli_code = _selectedKbli;
  _tableFilterState.aktivitas_code = _selectedAktivitas;

  // Toggle reset button visibility
  const resetBtn = document.getElementById("btnResetDate");
  if (resetBtn) {
    if (date_from || date_to) {
      resetBtn.classList.remove("hidden");
    } else {
      resetBtn.classList.add("hidden");
    }
  }

  currentPage = 1;
  loadBerita({ search, date_from, date_to });
}

function resetDateFilter() {
  document.getElementById("dateFrom").value = "";
  document.getElementById("dateTo").value = "";
  const resetBtn = document.getElementById("btnResetDate");
  if (resetBtn) resetBtn.classList.add("hidden");
  applyFilters();
}

// Keep backward-compat alias
function searchTable(query) {
  const searchInput = document.getElementById("searchInput");
  if (searchInput && query !== undefined) searchInput.value = query;
  applyFilters();
}

// ── Sort ──────────────────────────────────────────────────────────────────────

function applySortDate(arr) {
  arr.sort((a, b) => parseDateID(b.date) - parseDateID(a.date));
}

function sortTable(field) {
  const prevSortKey = _sortKeyUi;

  document
    .querySelectorAll(".th-sortable")
    .forEach((th) => th.classList.remove("active"));

  if (prevSortKey === field) {
    sortAsc = !sortAsc;
  } else {
    sortAsc = field !== "date"; // date: default desc (terbaru di atas)
  }
  _sortKeyUi = field;

  const sortFieldMap = {
    date: "date_parsed",
    title: "title",
    source: "source",
    tags: "tags",
  };
  const backendSortField = sortFieldMap[field] || "date_parsed";

  const thEl = document.querySelector(`[onclick="sortTable('${field}')"]`);
  if (thEl) {
    thEl.classList.add("active");
    const icon = document.getElementById(`sort-${field}`);
    if (icon) icon.textContent = sortAsc ? "↑" : "↓";
  }

  currentPage = 1;
  sortField = backendSortField;
  loadBerita();
}

// ── Download Excel ────────────────────────────────────────────────────────────

async function downloadExcel() {
  if (_tablePaginationState.total_items === 0) {
    alert("Belum ada data untuk diunduh.");
    return;
  }

  // Fetch ulang dengan kolom content (tidak ada di tabel biasa)
  let exportData = filteredData;
  try {
    const params = new URLSearchParams();
    // Ambil filter aktif saat ini
    const searchVal = (
      document.getElementById("searchInput")?.value || ""
    ).trim();
    const date_from = document.getElementById("dateFrom")?.value || "";
    const date_to = document.getElementById("dateTo")?.value || "";
    if (searchVal) params.set("search", searchVal);
    if (date_from) params.set("date_from", date_from);
    if (date_to) params.set("date_to", date_to);
    if (_selectedKbli) params.set("kbli_code", _selectedKbli);
    if (_selectedAktivitas) params.set("aktivitas_code", _selectedAktivitas);
    params.set("with_content", "1");

    const res = await fetch("/api/berita/export?" + params.toString());
    if (res.ok) {
      const json = await res.json();
      if (json.status === "ok") exportData = json.data;
    }
  } catch (e) {
    console.warn("Export fetch gagal, pakai data tabel saja:", e);
  }

  const rows = exportData.map((item, i) => ({
    No: i + 1,
    Judul: item.title || "",
    Sumber: item.source || "",
    Tanggal: item.date || "",
    URL: item.url || "",
    Tags: item.tags || "",
    KBLI: item.kbli || "",
    "Aktivitas Ekonomi": item.aktivitas_ekonomi || "",
    Konten: item.content || "",
  }));

  const ws = XLSX.utils.json_to_sheet(rows);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Berita");

  ws["!cols"] = [
    { wch: 5 },  // No
    { wch: 50 }, // Judul
    { wch: 15 }, // Sumber
    { wch: 25 }, // Tanggal
    { wch: 40 }, // URL
    { wch: 30 }, // Tags
    { wch: 48 }, // KBLI
    { wch: 55 }, // Aktivitas Ekonomi
    { wch: 80 }, // Konten
  ];

  XLSX.writeFile(wb, "berita_lokal_tegal.xlsx");
}

// ── AI Insights ───────────────────────────────────────────────────────────────

let _aiLoading        = false;
let _currentYear      = String(new Date().getFullYear()); // default tahun ini
let _aiInsightStream  = null;

// ── Custom Actor Dropdown ─────────────────────────────────────────────────────

let _currentActor = "bps";

const _ACTOR_LABELS = {
  bps:        "BPS",
  pemerintah: "Pemerintah (Bappeda)",
  akademisi:  "Akademisi",
};

const _ACTOR_SUBTITLE_LABELS = {
  bps:        "BPS",
  pemerintah: "Pemerintah (Bappeda/Bappenas)",
  akademisi:  "Akademisi / Peneliti",
};

function selectActor(value) {
  _currentActor = value;
  const label = document.getElementById("aiActorLabel");
  if (label) label.textContent = _ACTOR_LABELS[value] || value;
  const subtitleLabel = document.getElementById("aiActorSubtitleLabel");
  if (subtitleLabel) subtitleLabel.textContent = _ACTOR_SUBTITLE_LABELS[value] || value;
  document.querySelectorAll("#aiActorMenu .ai-period-option").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.value === value);
  });
  closeActorDropdown();
  loadAIInsights({ forceRefresh: false });
}

function toggleActorDropdown() {
  const menu = document.getElementById("aiActorMenu");
  const btn  = document.getElementById("aiActorBtn");
  if (!menu) return;
  const isOpen = menu.style.display !== "none";
  menu.style.display = isOpen ? "none" : "";
  btn?.classList.toggle("open", !isOpen);
}

function closeActorDropdown() {
  const menu = document.getElementById("aiActorMenu");
  const btn  = document.getElementById("aiActorBtn");
  if (menu) menu.style.display = "none";
  btn?.classList.remove("open");
}

// ── Custom Period Dropdown ────────────────────────────────────────────────────

let _currentPeriod = "";

function _getDefaultPeriod() {
  const month = new Date().getMonth() + 1;
  if (month <= 3) return "q1";
  if (month <= 6) return "q2";
  if (month <= 9) return "q3";
  return "q4";
}

const _PERIOD_LABELS = {
  q1: "Triwulan I (Jan–Mar)",
  q2: "Triwulan II (Apr–Jun)",
  q3: "Triwulan III (Jul–Sep)",
  q4: "Triwulan IV (Okt–Des)",
  s1: "Semester I (Jan–Jun)",
  s2: "Semester II (Jul–Des)",
  yearly: "Tahunan (Jan–Des)",
};

function _initPeriodDropdown() {
  if (_currentPeriod) return;
  const def = _getDefaultPeriod();
  _currentPeriod = def;
  const label = document.getElementById("aiPeriodLabel");
  if (label) label.textContent = _PERIOD_LABELS[def] || def;
  // Mark active option (hanya period dropdown, bukan actor)
  document.querySelectorAll("#aiPeriodMenu .ai-period-option").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.value === def);
  });
  // Close menus on outside click
  document.addEventListener("click", (e) => {
    const ddPeriod = document.getElementById("aiPeriodDropdown");
    if (ddPeriod && !ddPeriod.contains(e.target)) closePeriodDropdown();
    const ddActor = document.getElementById("aiActorDropdown");
    if (ddActor && !ddActor.contains(e.target)) closeActorDropdown();
  });
  // Isi dropdown tahun
  _initYearDropdown();
}

async function _initYearDropdown() {
  const menu = document.getElementById("aiYearMenu");
  const label = document.getElementById("aiYearLabel");
  if (!menu) return;
  try {
    const res = await fetch("/api/berita/years");
    const json = await res.json();
    const years =
      json.status === "ok" && json.years?.length ? json.years : [_currentYear];
    // Pastikan _currentYear valid
    if (!years.includes(_currentYear)) {
      _currentYear = years[0];
    }
    if (label) label.textContent = _currentYear;
    // Render opsi
    menu.innerHTML = years
      .map(
        (y) =>
          `<button class="ai-period-option${y === _currentYear ? " active" : ""}" 
                data-year="${y}" onclick="selectYear('${y}')">${y}</button>`,
      )
      .join("");
    // Close on outside click
    document.addEventListener(
      "click",
      (e) => {
        const dd = document.getElementById("aiYearDropdown");
        if (dd && !dd.contains(e.target)) closeYearDropdown();
      },
      { once: false },
    );
  } catch {
    if (label) label.textContent = _currentYear;
    menu.innerHTML = `<button class="ai-period-option active" onclick="selectYear('${_currentYear}')">${_currentYear}</button>`;
  }
}

function toggleYearDropdown() {
  const menu = document.getElementById("aiYearMenu");
  const btn = document.getElementById("aiYearBtn");
  if (!menu) return;
  const isOpen = menu.style.display !== "none";
  menu.style.display = isOpen ? "none" : "";
  btn?.classList.toggle("open", !isOpen);
}

function closeYearDropdown() {
  const menu = document.getElementById("aiYearMenu");
  const btn = document.getElementById("aiYearBtn");
  if (menu) menu.style.display = "none";
  btn?.classList.remove("open");
}

function selectYear(value) {
  _currentYear = value;
  // Update label
  const label = document.getElementById("aiYearLabel");
  if (label) label.textContent = value;
  // Update active state
  document.querySelectorAll("#aiYearMenu .ai-period-option").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.year === value);
  });
  closeYearDropdown();
  loadAIInsights({ forceRefresh: false });
}

function togglePeriodDropdown() {
  const menu = document.getElementById("aiPeriodMenu");
  const btn = document.getElementById("aiPeriodBtn");
  if (!menu) return;
  const isOpen = menu.style.display !== "none";
  menu.style.display = isOpen ? "none" : "";
  btn?.classList.toggle("open", !isOpen);
}

function closePeriodDropdown() {
  const menu = document.getElementById("aiPeriodMenu");
  const btn = document.getElementById("aiPeriodBtn");
  if (menu) menu.style.display = "none";
  btn?.classList.remove("open");
}

function selectPeriod(value, label) {
  _currentPeriod = value;
  const labelEl = document.getElementById("aiPeriodLabel");
  if (labelEl) labelEl.textContent = label;
  document.querySelectorAll(".ai-period-option").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.value === value);
  });
  closePeriodDropdown();
  loadAIInsights({ forceRefresh: false });
}

function setAILoading(loading, articleCount) {
  _aiLoading = loading;
  const btn = document.getElementById("btnRefreshAI");
  const statusBar = document.getElementById("aiLoadingStatus");
  const statusText = document.getElementById("aiLoadingText");
  const refreshTxt = document.getElementById("btnRefreshText");
  const icon = document.getElementById("refreshIcon");

  if (loading) {
    if (btn) {
      btn.classList.add("loading");
      btn.disabled = true;
    }
    if (refreshTxt) refreshTxt.textContent = "Memuat...";
    if (statusBar) statusBar.style.display = "";
    const n = articleCount ? `${articleCount}` : "";
    if (statusText)
      statusText.textContent = n
        ? `Menganalisis ${n} berita dengan Gemini AI...`
        : "Menganalisis berita dengan Gemini AI...";
    // Animasi pulse pada cards
    ["aiCardPdrb", "aiCardKemiskinan", "aiCardPengangguran"].forEach((id) => {
      document.getElementById(id)?.classList.add("ai-card-loading");
    });
  } else {
    if (btn) {
      btn.classList.remove("loading");
      btn.disabled = false;
    }
    if (refreshTxt) refreshTxt.textContent = "Refresh";
    if (statusBar) statusBar.style.display = "none";
    ["aiCardPdrb", "aiCardKemiskinan", "aiCardPengangguran"].forEach((id) => {
      document.getElementById(id)?.classList.remove("ai-card-loading");
    });
  }
}

function _showAISkeleton() {
  const skeletonHtml = `<div class="ai-skeleton">
        <div class="ai-skeleton-line"></div>
        <div class="ai-skeleton-line w80"></div>
        <div class="ai-skeleton-line w90"></div>
        <div class="ai-skeleton-line w70"></div>
    </div>`;
  ["aiBodyPdrb", "aiBodyKemiskinan", "aiBodyPengangguran"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = skeletonHtml;
  });
  // Sembunyikan sumber
  ["aiSourcesPdrb", "aiSourcesKemiskinan", "aiSourcesPengangguran"].forEach(
    (id) => {
      const el = document.getElementById(id);
      if (el) el.style.display = "none";
    },
  );
}

function _showAIError(message) {
  const errorHtml = `<div class="ai-error">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        ${escapeHtml(message)}
    </div>`;
  ["aiBodyPdrb", "aiBodyKemiskinan", "aiBodyPengangguran"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = errorHtml;
  });
}

function _renderSources(catKey, sources) {
  // catKey: "Pdrb" | "Kemiskinan" | "Pengangguran"
  const wrap = document.getElementById(`aiSources${catKey}`);
  const label = document.getElementById(`aiSourcesLabel${catKey}`);
  const list = document.getElementById(`aiSourcesList${catKey}`);
  if (!wrap || !label || !list) return;

  if (!sources || sources.length === 0) {
    wrap.style.display = "none";
    return;
  }

  label.textContent = `Sumber Berita (${sources.length})`;
  list.innerHTML = sources
    .map((s) => {
      const title = escapeHtml(s.title || "—");
      const url = escapeHtml(s.url || "#");
      const num = Number(s.num || 0) > 0 ? `<strong>[${Number(s.num)}]</strong> ` : "";
      return `<li><a href="${url}" target="_blank" rel="noopener noreferrer">${num}${title}</a></li>`;
    })
    .join("");
  wrap.style.display = "";
  list.style.display = "none"; // collapsed by default
}

function toggleSources(catKey) {
  const list = document.getElementById(`aiSourcesList${catKey}`);
  const btn = document.querySelector(`#aiSources${catKey} .ai-sources-toggle`);
  if (!list) return;
  const isOpen = list.style.display !== "none";
  list.style.display = isOpen ? "none" : "";
  if (btn) btn.classList.toggle("open", !isOpen);
}

function _buildSourceMapByTag(sourceList = []) {
  const map = {};
  if (!Array.isArray(sourceList)) return map;
  sourceList.forEach((s, idx) => {
    const tag = String(s?.tag_id || "").toUpperCase();
    if (!tag) return;
    map[tag] = {
      ...s,
      num: Number(s.num || 0) > 0 ? Number(s.num) : idx + 1,
    };
  });
  return map;
}

function _renderInsightCitationLink(source) {
  const num = Number(source?.num || 0) > 0 ? Number(source.num) : 1;
  const url = escapeHtml(source?.url || "#");
  const title = escapeHtml(source?.title || "Sumber berita");
  return `<a class="ai-cite" href="${url}" target="_blank" rel="noopener noreferrer" title="${title}">${num}</a>`;
}

function _renderInsightMarkdownHtml(text, sourceMapByTag = {}) {
  const raw = String(text || "");

  // Backward compatibility: data lama dari backend sudah berupa HTML inline citation
  if (raw.includes("<a") && raw.includes("ai-cite")) {
    return `<div class="ai-insight-text md-content">${raw}</div>`;
  }

  const normalized = _normalizeCitationMarkers(raw, "PKT");
  let html = _markdownToHtmlSafe(normalized);

  // Jika map tersedia, ganti marker [P01]/[K01]/[T01] menjadi link angka inline.
  if (sourceMapByTag && Object.keys(sourceMapByTag).length > 0) {
    html = html.replace(/\[([PKT]\d{2})\]/gi, (_, rawId) => {
      const tag = String(rawId || "").toUpperCase();
      const src = sourceMapByTag[tag];
      if (!src) return "";
      return _renderInsightCitationLink(src);
    });
  }

  return `<div class="ai-insight-text md-content">${html}</div>`;
}

function renderAIInsights(json) {
  const { data, article_count: count, quarter, sources = {} } = json;

  // Teks insight (render langsung; streaming token ditangani event SSE delta)
  const categoryMap = {
    aiBodyPdrb: data?.pdrb || "—",
    aiBodyKemiskinan: data?.kemiskinan || "—",
    aiBodyPengangguran: data?.pengangguran || "—",
  };

  Object.entries(categoryMap).forEach(([id, text]) => {
    const el = document.getElementById(id);
    if (!el) return;

    const catKey =
      id === "aiBodyPdrb"
        ? "pdrb"
        : id === "aiBodyKemiskinan"
        ? "kemiskinan"
        : "pengangguran";
    const map = _buildSourceMapByTag(sources[catKey] || []);
    el.innerHTML = _renderInsightMarkdownHtml(text || "—", map);
  });

  // Label periode
  const quarterEl = document.getElementById("aiQuarterLabel");
  if (quarterEl) quarterEl.textContent = quarter || "periode ini";

  // Label aktor di subtitle
  const actorSubtitleEl = document.getElementById("aiActorSubtitleLabel");
  if (actorSubtitleEl) actorSubtitleEl.textContent = _ACTOR_SUBTITLE_LABELS[_currentActor] || _ACTOR_LABELS[_currentActor] || "BPS";

  // Badge jumlah berita
  const countBadge = document.getElementById("aiArticleCount");
  const countText = document.getElementById("aiArticleCountText");
  if (countBadge && countText) {
    countText.textContent = `${count} berita dianalisis`;
    countBadge.style.display = count ? "" : "none";
  }

  // Sumber berita per kategori
  _renderSources("Pdrb", sources.pdrb || []);
  _renderSources("Kemiskinan", sources.kemiskinan || []);
  _renderSources("Pengangguran", sources.pengangguran || []);
}

async function loadAIInsights({
  forceRefresh = false,
  period = "",
} = {}) {
  if (_aiLoading) return;

  if (_aiInsightStream) {
    _aiInsightStream.close();
    _aiInsightStream = null;
  }

  _initPeriodDropdown();
  const selectedPeriod = period || _currentPeriod || _getDefaultPeriod();

  // ── Cek sessionStorage terlebih dahulu ────────────────────────────────────
  // Tujuan: hindari hit backend setiap kali user kembali ke halaman
  // dalam sesi browser yang sama.
  // forceRefresh bypass cache karena butuh data segar.
  if (!forceRefresh) {
    const cacheKey = `ai_insights_v2_${_currentActor}_${selectedPeriod}_${_currentYear || ""}`;
    try {
      const raw = sessionStorage.getItem(cacheKey);
      if (raw) {
        const cached = JSON.parse(raw);
        if (cached && cached.status === "ok") {
          renderAIInsights(cached);
          return; // ← langsung render, tidak hit backend sama sekali
        }
      }
    } catch (_) {
      /* abaikan error parse / storage penuh */
    }
  }

  setAILoading(true);
  if (!forceRefresh) _showAISkeleton();

  try {
    const params = new URLSearchParams({ period: selectedPeriod });
    if (forceRefresh) params.set("refresh", "1");
    if (_currentYear)  params.set("year", _currentYear);
    params.set("actor", _currentActor);
    const url = "/api/ai-insights/stream?" + params.toString();

    const streamState = {
      pdrb: "",
      kemiskinan: "",
      pengangguran: "",
      sourceMap: {
        pdrb: {},
        kemiskinan: {},
        pengangguran: {},
      },
      sources: {
        pdrb: [],
        kemiskinan: [],
        pengangguran: [],
      },
      quarter: "",
      article_count: 0,
      done: false,
    };

    const categoryToElement = {
      pdrb: "aiBodyPdrb",
      kemiskinan: "aiBodyKemiskinan",
      pengangguran: "aiBodyPengangguran",
    };

    _aiInsightStream = new EventSource(url);

    await new Promise((resolve, reject) => {
      _aiInsightStream.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data || "{}");
          const statusText = document.getElementById("aiLoadingText");

          if (payload.type === "start") {
            streamState.article_count = Number(payload.article_count || 0);
            streamState.quarter = payload.quarter || "periode ini";
            if (statusText) {
              statusText.textContent = `Insight AI sedang dibuat (${streamState.article_count} berita)...`;
            }
            return;
          }

          if (payload.type === "category_start") {
            const cat = payload.category;
            streamState.sourceMap[cat] = _buildSourceMapByTag(payload.source_map || []);
            return;
          }

          if (payload.type === "delta") {
            const cat = payload.category;
            streamState[cat] = (streamState[cat] || "") + (payload.text || "");
            const el = document.getElementById(categoryToElement[cat]);
            if (el) {
              el.innerHTML = _renderInsightMarkdownHtml(
                streamState[cat],
                streamState.sourceMap[cat] || {},
              );
            }
            return;
          }

          if (payload.type === "category_done") {
            const cat = payload.category;
            streamState[cat] = payload.text || streamState[cat] || "";
            streamState.sources[cat] = payload.sources || [];
            const el = document.getElementById(categoryToElement[cat]);
            if (el) {
              el.innerHTML = _renderInsightMarkdownHtml(
                streamState[cat],
                streamState.sourceMap[cat] || {},
              );
            }
            return;
          }

          if (payload.type === "done") {
            const finalJson = {
              status: payload.status || "ok",
              cached: !!payload.cached,
              quarter: payload.quarter || streamState.quarter,
              article_count: payload.article_count ?? streamState.article_count,
              data: payload.data || {
                pdrb: streamState.pdrb,
                kemiskinan: streamState.kemiskinan,
                pengangguran: streamState.pengangguran,
              },
              sources: payload.sources || streamState.sources,
            };

            renderAIInsights(finalJson);

            try {
              const cacheKey = `ai_insights_v2_${_currentActor}_${selectedPeriod}_${_currentYear || ""}`;
              sessionStorage.setItem(cacheKey, JSON.stringify(finalJson));
            } catch (_) {
              // ignore
            }

            if (statusText) {
              statusText.textContent = `Selesai — ${finalJson.article_count || 0} berita dianalisis.`;
            }

            streamState.done = true;
            resolve();
            return;
          }

          if (payload.type === "error") {
            reject(new Error(payload.message || "Gagal memuat insight AI."));
          }
        } catch (err) {
          reject(err);
        }
      };

      _aiInsightStream.onerror = () => {
        if (!streamState.done) {
          reject(new Error("Koneksi stream terputus saat memuat insight AI."));
        }
      };
    });
  } catch (err) {
    _showAIError("Gagal menghubungi server. Coba refresh halaman.");
    console.error("AI Insights error:", err);
  } finally {
    if (_aiInsightStream) {
      _aiInsightStream.close();
      _aiInsightStream = null;
    }
    setAILoading(false);
  }
}

function refreshAIInsights() {
  if (_aiInsightStream) {
    _aiInsightStream.close();
    _aiInsightStream = null;
  }
  // Hapus cache sessionStorage untuk periode yang sedang aktif,
  // agar forceRefresh benar-benar mengambil data segar dari backend.
  try {
    const p = _currentPeriod || _getDefaultPeriod();
    sessionStorage.removeItem(`ai_insights_v2_${_currentActor}_${p}_${_currentYear || ""}`);
  } catch (_) {
    /* abaikan */
  }
  loadAIInsights({ forceRefresh: true });
}

// ── Floating AI Chat (RAG) ────────────────────────────────────────────────────

let _chatLoading = false;
let _chatSessionId = "";
let _chatModalResolver = null;
let _chatReady = false;

async function _ensureChatReady() {
  if (_chatReady) return;
  try {
    const fromStorage = localStorage.getItem(_chatStorageKey());
    if (fromStorage && /^\d+$/.test(fromStorage)) {
      _chatSessionId = fromStorage;
    } else {
      await _ensureChatSession(false);
    }
    await _loadChatHistory();
    _chatReady = true;
  } catch (err) {
    _showChatEmptyState();
    console.error("Gagal memuat sesi chat:", err);
  }
}

function _chatStorageKey() {
  const username = currentUser?.username || "anon";
  return `bps_chat_session_${username}`;
}

function initFloatingChat() {
  const input = document.getElementById("chatInput");
  if (!input) return;

  _initChatModal();

  // Shift+Enter = baris baru, Enter = kirim
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChatMessage(e);
    }
  });

  const chatView = document.getElementById("chatWindow");
  if (chatView) {
    chatView.classList.add("open");
  }
}

function _chatModalElements() {
  return {
    backdrop: document.getElementById("chatModalBackdrop"),
    title: document.getElementById("chatModalTitle"),
    message: document.getElementById("chatModalMessage"),
    cancelBtn: document.getElementById("chatModalCancelBtn"),
    confirmBtn: document.getElementById("chatModalConfirmBtn"),
  };
}

function _initChatModal() {
  const { backdrop, cancelBtn, confirmBtn } = _chatModalElements();
  if (!backdrop || backdrop.dataset.init === "1") return;

  // Pastikan modal tidak terbuka saat initial load.
  backdrop.hidden = true;

  const close = (result) => {
    backdrop.hidden = true;
    document.body.style.overflow = "";
    const resolver = _chatModalResolver;
    _chatModalResolver = null;
    if (resolver) resolver(result);
  };

  cancelBtn?.addEventListener("click", () => close(false));
  confirmBtn?.addEventListener("click", () => close(true));

  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) close(false);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !backdrop.hidden) close(false);
  });

  backdrop.dataset.init = "1";
}

function showChatDialog({
  title = "Konfirmasi",
  message = "",
  confirmText = "Lanjutkan",
  cancelText = "Batal",
  showCancel = true,
  danger = false,
} = {}) {
  const { backdrop, title: titleEl, message: msgEl, cancelBtn, confirmBtn } = _chatModalElements();
  if (!backdrop || !titleEl || !msgEl || !confirmBtn) {
    return Promise.resolve(false);
  }

  titleEl.textContent = title;
  msgEl.textContent = message;
  confirmBtn.textContent = confirmText;
  confirmBtn.classList.toggle("danger", !!danger);

  if (cancelBtn) {
    cancelBtn.textContent = cancelText;
    cancelBtn.style.display = showCancel ? "" : "none";
  }

  backdrop.hidden = false;
  document.body.style.overflow = "hidden";

  return new Promise((resolve) => {
    _chatModalResolver = resolve;
  });
}

async function _ensureChatSession(forceNew = false) {
  const body = { new: !!forceNew };
  const res = await fetch("/api/ai-chat/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status === 401) {
    window.location.href = "/login";
    return "";
  }
  const json = await res.json();
  if (json.status !== "ok" || !json.session?.id) {
    throw new Error(json.message || "Gagal membuat session chat.");
  }
  _chatSessionId = String(json.session.id);
  localStorage.setItem(_chatStorageKey(), _chatSessionId);
  return _chatSessionId;
}

async function _loadChatHistory() {
  if (!_chatSessionId) return;
  const body = document.getElementById("chatBody");
  if (!body) return;

  const qs = new URLSearchParams({ session_id: _chatSessionId }).toString();
  const res = await fetch(`/api/ai-chat/history?${qs}`);
  if (res.status === 401) {
    window.location.href = "/login";
    return;
  }
  const json = await res.json();
  if (json.status !== "ok") return;

  body.innerHTML = "";
  const history = json.history || [];
  if (history.length === 0) {
    _showChatEmptyState();
    return;
  }

  history.forEach((item) => {
    _appendChatMessage(item.role, item.content, item.citations_json || []);
  });
  _scrollChatToBottom();
}

function _showChatEmptyState() {
  const body = document.getElementById("chatBody");
  if (!body) return;
  body.innerHTML = `
    <div class="chat-msg assistant" id="chatEmptyState">
      <img class="chat-avatar" src="/static/logochatbotAI.png" alt="AI">
      <div class="chat-bubble">
        Halo! Saya siap membantu Anda menganalisis berita terkait kondisi ekonomi,
        kemiskinan, dan pengangguran di Kabupaten Tegal.<br><br>
        Silakan ajukan pertanyaan, misalnya:<br>
        &bull; Apa penyebab kenaikan kemiskinan bulan lalu?<br>
        &bull; Bagaimana tren PDRB sektor industri saat ini?<br>
        &bull; Sektor KBLI apa yang paling terdampak PHK?
      </div>
    </div>`;
}

function _toggleChatLoading(loading) {
  _chatLoading = loading;
  const typing = document.getElementById("chatTyping");
  const btn = document.getElementById("chatSendBtn");
  const input = document.getElementById("chatInput");
  if (typing) typing.style.display = loading ? "inline-flex" : "none";
  if (btn) btn.disabled = loading;
  if (input) input.disabled = loading;
}

function _scrollChatToBottom() {
  const body = document.getElementById("chatBody");
  if (!body) return;
  body.scrollTop = body.scrollHeight;
}

function _buildCitationMap(citations = []) {
  const map = {};
  if (!Array.isArray(citations)) return map;
  citations.forEach((c, idx) => {
    const key = String(c?.cite_id || "").toUpperCase();
    if (!key) return;
    map[key] = {
      ...c,
      num: Number(c?.num || 0) > 0 ? Number(c.num) : idx + 1,
    };
  });
  return map;
}

function _renderInlineCitationIcon(citation) {
  const cid = escapeHtml(citation?.cite_id || "S??");
  const url = escapeHtml(citation?.url || "#");
  const title = escapeHtml(citation?.title || "Sumber berita");
  const num = Number(citation?.num || 0) > 0 ? Number(citation.num) : 1;
  return `<a class="ai-cite chat-inline-cite" href="${url}" target="_blank" rel="noopener noreferrer" title="${title}">${num}<span class="sr-only">${cid}</span></a>`;
}

function _renderChatText(text, citations = []) {
  const citationMap = _buildCitationMap(citations);
  const normalized = _normalizeCitationMarkers(text || "", "S");
  let html = _markdownToHtmlSafe(normalized);
  html = html.replace(/\[(S\d{2})\]/gi, (_, rawId) => {
    const cid = String(rawId || "").toUpperCase();
    const citation = citationMap[cid];
    if (!citation) return "";
    return _renderInlineCitationIcon(citation);
  });
  return `<div class="md-content">${html}</div>`;
}

function _appendChatMessage(role, content, citations = []) {
  const body = document.getElementById("chatBody");
  if (!body) return null;

  const empty = document.getElementById("chatEmptyState");
  if (empty) empty.remove();

  const wrap = document.createElement("div");
  wrap.className = `chat-msg ${role === "user" ? "user" : "assistant"}`;

  const avatarHtml = role !== "user"
    ? `<img class="chat-avatar" src="/static/logochatbotAI.png" alt="AI">`
    : "";

  wrap.innerHTML = `${avatarHtml}<div class="chat-bubble">${_renderChatText(content, citations)}</div>`;
  body.appendChild(wrap);
  _scrollChatToBottom();
  return wrap.querySelector(".chat-bubble");
}

async function toggleChatWindow() {
  _openView("chat", { updateHash: true });
}

function closeChatWindow() {
  _openView("overview", { updateHash: true });
}

async function clearChatConversation() {
  if (!_chatSessionId) {
    await _ensureChatSession(false);
  }
  if (!_chatSessionId) return;

  const ok = await showChatDialog({
    title: "Hapus Percakapan?",
    message:
      "Semua pesan dalam sesi chat ini akan dihapus permanen. Tindakan ini tidak bisa dibatalkan.",
    confirmText: "Ya, Hapus",
    cancelText: "Batal",
    showCancel: true,
    danger: true,
  });
  if (!ok) return;

  try {
    const res = await fetch("/api/ai-chat/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: _chatSessionId }),
    });
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const json = await res.json();
    if (json.status !== "ok") {
      await showChatDialog({
        title: "Gagal Menghapus",
        message: json.message || "Gagal menghapus percakapan.",
        confirmText: "Tutup",
        showCancel: false,
      });
      return;
    }
    _showChatEmptyState();
    await showChatDialog({
      title: "Berhasil",
      message: "Percakapan berhasil dibersihkan.",
      confirmText: "Oke",
      showCancel: false,
    });
  } catch (err) {
    await showChatDialog({
      title: "Terjadi Kendala",
      message: "Gagal menghapus percakapan: " + err.message,
      confirmText: "Tutup",
      showCancel: false,
    });
  }
}

/**
 * Hapus blok [PERTANYAAN: ...] dari teks sebelum ditampilkan ke user.
 * Blok ini disisipkan LLM di akhir jawaban dan di-parse terpisah di backend.
 * Stripping di sisi JS juga sebagai safety-net saat streaming berlangsung.
 */
function _stripFollowUpBlock(text) {
  return (text || "").replace(/\[PERTANYAAN:.*?\]/gis, "").trim();
}

/**
 * Render tombol pertanyaan lanjutan di bawah bubble AI.
 * @param {HTMLElement} msgWrap  — elemen .chat-msg.assistant
 * @param {string[]}    questions — array 1-3 pertanyaan
 */
function _appendFollowUps(msgWrap, questions) {
  if (!msgWrap || !questions?.length) return;

  const container = document.createElement("div");
  container.className = "chat-followups";

  questions.forEach((q) => {
    const btn = document.createElement("button");
    btn.className   = "chat-followup-btn";
    btn.type        = "button";
    btn.textContent = q;
    btn.title       = "Klik untuk mengirim pertanyaan ini";
    btn.onclick     = () => {
      // Hapus semua chip follow-up agar chat tidak penuh
      document.querySelectorAll(".chat-followups").forEach((el) => el.remove());
      _sendFollowUp(q);
    };
    container.appendChild(btn);
  });

  msgWrap.appendChild(container);
  _scrollChatToBottom();
}

/**
 * Isi chatInput dengan pertanyaan dan langsung kirim.
 */
function _sendFollowUp(question) {
  const input = document.getElementById("chatInput");
  if (!input || _chatLoading) return;
  input.value = question;
  sendChatMessage(null);
}

async function sendChatMessage(event) {
  if (event) event.preventDefault();
  if (_chatLoading) return;

  const input = document.getElementById("chatInput");
  if (!input) return;

  const message = (input.value || "").trim();
  if (!message) return;

  if (message.length > 1200) {
    alert("Pesan terlalu panjang. Maksimal 1200 karakter.");
    return;
  }

  try {
    if (!_chatSessionId) {
      await _ensureChatSession(false);
    }

    _appendChatMessage("user", message, []);
    input.value = "";
    _toggleChatLoading(true);

    const assistantBubble = _appendChatMessage("assistant", "", []);
    let streamedText = "";
    let activeCitations = [];

    const res = await fetch("/api/ai-chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: _chatSessionId,
        message,
      }),
    });

    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }

    if (!res.ok || !res.body) {
      let errMessage = "Terjadi kendala saat memproses chat.";
      try {
        const fallback = await res.json();
        errMessage = fallback.message || errMessage;
      } catch (_) {
        // noop
      }
      if (assistantBubble) {
        assistantBubble.innerHTML = _renderChatText(errMessage, []);
      }
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    // Label "outer" dipakai agar inner-loop bisa langsung membreak outer-loop
    // ketika event "done" atau "error" diterima.
    // Ini penting untuk Vercel serverless: koneksi HTTP tidak selalu ditutup
    // setelah generator Flask selesai, sehingga reader.read() bisa hang selamanya
    // meski semua data sudah diterima. Dengan break berbasis event aplikasi (bukan
    // bergantung pada penutupan stream), UI selalu kembali normal setelah respons.
    outer: while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const rawEvent = buffer.slice(0, boundary).trim();
        buffer = buffer.slice(boundary + 2);

        if (rawEvent) {
          const dataLines = rawEvent
            .split("\n")
            .filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5).trim());

          if (dataLines.length > 0) {
            const dataStr = dataLines.join("");
            try {
              const payload = JSON.parse(dataStr);

              if (payload.type === "start") {
                if (payload.session_id) {
                  _chatSessionId = String(payload.session_id);
                  localStorage.setItem(_chatStorageKey(), _chatSessionId);
                }
                if (Array.isArray(payload.sources)) {
                  activeCitations = payload.sources;
                }
              } else if (payload.type === "delta") {
                streamedText += payload.text || "";
                if (assistantBubble) {
                  // Strip blok [PERTANYAAN: ...] agar tidak tampil saat streaming
                  assistantBubble.innerHTML = _renderChatText(
                    _stripFollowUpBlock(streamedText),
                    activeCitations,
                  );
                }
                _scrollChatToBottom();
              } else if (payload.type === "done") {
                if (payload.session_id) {
                  _chatSessionId = String(payload.session_id);
                  localStorage.setItem(_chatStorageKey(), _chatSessionId);
                }
                if (Array.isArray(payload.citations) && payload.citations.length > 0) {
                  activeCitations = payload.citations;
                }
                if (assistantBubble) {
                  assistantBubble.innerHTML = _renderChatText(
                    _stripFollowUpBlock(streamedText),
                    activeCitations,
                  );
                }
                // Render tombol pertanyaan lanjutan
                if (Array.isArray(payload.follow_ups) && payload.follow_ups.length > 0) {
                  _appendFollowUps(assistantBubble?.parentElement, payload.follow_ups);
                }
                // Keluar dari loop segera setelah event "done" — jangan tunggu
                // stream ditutup dari sisi server (tidak reliable di Vercel serverless)
                reader.cancel().catch(() => {});
                break outer;
              } else if (payload.type === "error") {
                const msg = payload.message || "Terjadi kendala saat memproses chat.";
                if (assistantBubble) {
                  assistantBubble.innerHTML = _renderChatText(msg, []);
                }
                // Sama seperti "done" — keluar segera
                reader.cancel().catch(() => {});
                break outer;
              }
            } catch (_) {
              // Abaikan frame SSE yang tidak valid
            }
          }
        }

        boundary = buffer.indexOf("\n\n");
      }
    }

    if (!streamedText && assistantBubble) {
      assistantBubble.innerHTML = _renderChatText(
        "Tidak ada respons dari server AI. Silakan coba lagi.",
        [],
      );
    }
  } catch (err) {
    _appendChatMessage("assistant", "Gagal menghubungi server AI chat. Silakan coba lagi.", []);
    console.error("Chat error:", err);
  } finally {
    _toggleChatLoading(false);
    const inputAfter = document.getElementById("chatInput");
    if (inputAfter) inputAfter.focus();
  }
}
