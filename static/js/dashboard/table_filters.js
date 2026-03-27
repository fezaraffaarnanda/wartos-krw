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

// ── PDRB Pengeluaran Filter ───────────────────────────────────────────────────

function populatePdrbPengeluaranFilter() {
  const menu = document.getElementById("pdrbPengeluaranFilterMenu");
  if (!menu) return;

  const codeArr = _filterOptions.pdrb_pengeluaran_codes || [];
  if (codeArr.length === 0) {
    menu.innerHTML = `<div style="padding:10px 14px;font-size:0.8rem;color:var(--text-muted)">Belum ada data PDRB pengeluaran</div>`;
    return;
  }

  let html = `<button class="kbli-filter-clear" onclick="clearPdrbPengeluaranFilter()">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        Tampilkan Semua
    </button>
    <div class="kbli-filter-sep"></div>`;

  codeArr.forEach((code) => {
    const label = PDRB_PENGELUARAN_LABELS[code] || code;
    const parentCode = getPdrbPengeluaranParentCode(code);
    const parentLabel = PDRB_PENGELUARAN_PARENT_LABELS[parentCode] || parentCode;
    const selectedCls = _selectedPdrbPengeluaran === code ? " selected" : "";
    html += `<button class="kbli-filter-option${selectedCls}" onclick="selectPdrbPengeluaranFilter('${code}')">
            <span class="pdrb-filter-code">${escapeHtml(code)}</span>
            <span>${escapeHtml(label)}${parentLabel ? ` <small>(${escapeHtml(parentLabel)})</small>` : ""}</span>
        </button>`;
  });

  menu.innerHTML = html;
}

function togglePdrbPengeluaranFilter() {
  const menu = document.getElementById("pdrbPengeluaranFilterMenu");
  const btn = document.getElementById("pdrbPengeluaranFilterBtn");
  if (!menu || !btn) return;
  const isOpen = menu.classList.contains("open");
  if (isOpen) {
    menu.classList.remove("open");
    btn.classList.remove("open");
  } else {
    populatePdrbPengeluaranFilter();
    menu.classList.add("open");
    btn.classList.add("open");
  }
}

function selectPdrbPengeluaranFilter(code) {
  _selectedPdrbPengeluaran = code;
  _tableFilterState.pdrb_pengeluaran_code = code;
  const btn = document.getElementById("pdrbPengeluaranFilterBtn");
  const dot = document.getElementById("pdrbPengeluaranFilterDot");
  const label = document.getElementById("pdrbPengeluaranFilterLabel");
  if (label) label.textContent = code;
  if (dot) dot.style.display = "";
  if (btn) btn.classList.add("active");

  const menu = document.getElementById("pdrbPengeluaranFilterMenu");
  if (menu) {
    menu.classList.remove("open");
    btn?.classList.remove("open");
  }

  currentPage = 1;
  applyFilters();
}

function clearPdrbPengeluaranFilter() {
  _selectedPdrbPengeluaran = "";
  _tableFilterState.pdrb_pengeluaran_code = "";
  const btn = document.getElementById("pdrbPengeluaranFilterBtn");
  const dot = document.getElementById("pdrbPengeluaranFilterDot");
  const label = document.getElementById("pdrbPengeluaranFilterLabel");
  if (label) label.textContent = "Filter PDRB Pengeluaran";
  if (dot) dot.style.display = "none";
  if (btn) btn.classList.remove("active");

  const menu = document.getElementById("pdrbPengeluaranFilterMenu");
  if (menu) {
    menu.classList.remove("open");
    btn?.classList.remove("open");
  }

  currentPage = 1;
  applyFilters();
}

document.addEventListener("click", (e) => {
  const wrapper = document.getElementById("pdrbPengeluaranFilterWrapper");
  if (wrapper && !wrapper.contains(e.target)) {
    const menu = document.getElementById("pdrbPengeluaranFilterMenu");
    const btn = document.getElementById("pdrbPengeluaranFilterBtn");
    if (menu) menu.classList.remove("open");
    if (btn) btn.classList.remove("open");
  }
});
