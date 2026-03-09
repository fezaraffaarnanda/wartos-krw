/* ============================================
   Dashboard Berita — Frontend Logic
   5 Sumber: Radar Tegal, Pantura Post, Tribun Jateng, Kompas, Setda Tegal
   ============================================ */

let allData = [];
let filteredData = [];
let currentPage = 1;
const PER_PAGE = 15;
let sortField = "date";
let sortAsc = false;  // default: terbaru di atas
let currentUser = null;

const BULAN_ID = {
    januari: 0, februari: 1, maret: 2, april: 3, mei: 4, juni: 5,
    juli: 6, agustus: 7, september: 8, oktober: 9, november: 10, desember: 11,
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
let chartInstance = null;
let clockTimer = null;
let pollTimer = null;
let refreshTimer = null;  // auto-refresh untuk last scrape & data
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
            timeText = dt.toLocaleString("id-ID", {
                day:      "2-digit",
                month:    "long",
                year:     "numeric",
                hour:     "2-digit",
                minute:   "2-digit",
                timeZone: "Asia/Jakarta",
            }) + " WIB";
        }

        // ── Format berita baru ────────────────────────────────────────────────
        const count = (json.status === "ok" && json.new_count != null) ? json.new_count : 0;
        const newText = count > 0
            ? `${count} berita baru hari ini`
            : "Belum ada berita baru hari ini";

        // ── Isi elemen admin (scrapeSection) ─────────────────────────────────
        const elAdmin = document.getElementById("lastScrapeTime");
        if (elAdmin) elAdmin.textContent = timeText;

        const badgeAdmin = document.getElementById("newArticlesBadge");
        const textAdmin  = document.getElementById("newArticlesText");
        if (badgeAdmin && textAdmin) {
            textAdmin.textContent  = newText;
            badgeAdmin.style.display = "";
        }

        // ── Isi elemen info bar (semua user) ──────────────────────────────────
        const elUser = document.getElementById("lastScrapeTimeUser");
        if (elUser) elUser.textContent = timeText;

        const badgeUser = document.getElementById("newArticlesBadgeUser");
        const textUser  = document.getElementById("newArticlesTextUser");
        if (badgeUser && textUser) {
            textUser.textContent   = newText;
            badgeUser.style.display = "";
        }

    } catch (e) {
        ["lastScrapeTime", "lastScrapeTimeUser"].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.textContent = "—";
        });
    }
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
    startRealtimeClock();
    await loadUserInfo();
    loadBerita();
    loadLastScrape();
    loadAIInsights();
    animateCards();
    startAutoRefresh();
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
        await loadBerita();
    }, AUTO_REFRESH_MS);
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
            currentUser = json;
            const userEl = document.getElementById("headerUser");
            if (userEl) userEl.textContent = json.username;

            // Admin: sembunyikan info bar (sudah ada di scrape card)
            // Non-admin: sembunyikan scrape section
            if (json.role === "admin") {
                const infoBar = document.getElementById("scrapeInfoBar");
                if (infoBar) infoBar.style.display = "none";
            } else {
                const scrapeSection = document.getElementById("scrapeSection");
                if (scrapeSection) scrapeSection.style.display = "none";
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
        const params = new URLSearchParams();
        if (search)    params.set("search",    search);
        if (date_from) params.set("date_from", date_from);
        if (date_to)   params.set("date_to",   date_to);

        const url = "/api/berita" + (params.toString() ? "?" + params.toString() : "");
        const res = await fetch(url);
        if (res.status === 401) { window.location.href = "/login"; return; }
        const json = await res.json();
        if (json.status === "ok") {
            allData      = json.data || [];
            filteredData = [...allData];  // sudah difilter di server
            currentPage  = 1;
            updateSummary();
            renderTable();
            renderChart();
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

        if (res.status === 401) { window.location.href = "/login"; return; }

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
        if (res.status === 401) { window.location.href = "/login"; return; }
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

const SOURCE_KEYS = ["radartegal", "panturapost", "tribunjateng", "kompas", "setdategal"];

function resetProgressBars() {
    document.getElementById("progressSubtitle").textContent = "Memulai...";
    SOURCE_KEYS.forEach(key => {
        document.getElementById(`bar-${key}`).style.width = "0%";
        document.getElementById(`bar-${key}`).className = "progress-bar-fill";
        document.getElementById(`count-${key}`).textContent = "0";
        document.getElementById(`status-${key}`).textContent = "Menunggu...";
    });
}

function updateProgressUI(progress, overall) {
    const max = maxArticlesGlobal || 150;
    let runningSource = "";

    SOURCE_KEYS.forEach(key => {
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
            radartegal:   "Radar Tegal",
            panturapost:  "Pantura Post",
            tribunjateng: "Tribun Jateng",
            kompas:       "Kompas",
            setdategal:   "Setda Tegal",
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

    SOURCE_KEYS.forEach(key => {
        const bar = document.getElementById(`bar-${key}`);
        if (bar.className.includes("running")) {
            bar.className = "progress-bar-fill done";
            bar.style.width = "100%";
        }
    });

    if (overall.error) {
        alert("Scraping selesai dengan error: " + overall.error);
    }

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
    document.getElementById("totalBerita").textContent = allData.length;

    const tagCount = {};
    allData.forEach(item => {
        if (!item.tags) return;
        item.tags.split(/\s*\|\s*|,\s*/).forEach(t => {
            const tag = t.trim().replace(/^#/, "");
            if (tag) tagCount[tag] = (tagCount[tag] || 0) + 1;
        });
    });

    document.getElementById("totalTags").textContent = Object.keys(tagCount).length;

    const sorted = Object.entries(tagCount).sort((a, b) => b[1] - a[1]);
    const topEl = document.getElementById("topTag");
    if (sorted.length > 0) {
        topEl.textContent = sorted[0][0];
        topEl.classList.add("text-value");
    } else {
        topEl.textContent = "—";
    }

    const latestEl = document.getElementById("tanggalTerbaru");
    latestEl.textContent = (allData.length > 0 && allData[0].date) ? allData[0].date : "—";
}

// ── Chart ─────────────────────────────────────────────────────────────────────

const BULAN_NAMA_ID = [
    "Januari","Februari","Maret","April","Mei","Juni",
    "Juli","Agustus","September","Oktober","November","Desember"
];

function renderChart() {
    const now         = new Date();
    const thisYear    = now.getFullYear();
    const thisMonth   = now.getMonth(); // 0-based

    // ── Filter artikel bulan berjalan ─────────────────────────────────────────
    // Gunakan date_parsed (YYYY-MM-DD) kalau ada, fallback ke parse string date
    const prefix = `${thisYear}-${String(thisMonth + 1).padStart(2, "0")}-`;

    const monthData = allData.filter(item => {
        if (item.date_parsed) {
            return String(item.date_parsed).startsWith(prefix);
        }
        // fallback: parse dari string date ("7 Maret 2026, 14:30 WIB")
        const d = parseDateID(item.date);
        return d.getFullYear() === thisYear && d.getMonth() === thisMonth;
    });

    // ── Hitung frekuensi tag ──────────────────────────────────────────────────
    const tagCount = {};
    monthData.forEach(item => {
        if (!item.tags) return;
        item.tags.split(/\s*\|\s*|,\s*/).forEach(t => {
            const tag = t.trim().replace(/^#/, "").toLowerCase();
            if (tag) tagCount[tag] = (tagCount[tag] || 0) + 1;
        });
    });

    // ── Top 5 ─────────────────────────────────────────────────────────────────
    const sorted     = Object.entries(tagCount).sort((a, b) => b[1] - a[1]).slice(0, 5);
    const fullLabels = sorted.map(e => e[0]);
    const values     = sorted.map(e => e[1]);

    // Truncate label panjang
    const MAX_LABEL     = 26;
    const displayLabels = fullLabels.map(l => l.length > MAX_LABEL ? l.slice(0, MAX_LABEL) + "…" : l);

    // Update label bulan di header
    const monthEl = document.getElementById("chartMonthLabel");
    if (monthEl) monthEl.textContent = `${BULAN_NAMA_ID[thisMonth]} ${thisYear}`;

    const canvas = document.getElementById("chartTags");
    if (!canvas) return;
    if (chartInstance) chartInstance.destroy();

    if (sorted.length === 0) {
        // Tidak ada data bulan ini — tampilkan pesan kosong
        if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
        canvas.style.display = "none";
        let empty = document.getElementById("chartEmpty");
        if (!empty) {
            empty = document.createElement("p");
            empty.id = "chartEmpty";
            empty.style.cssText = "text-align:center;color:#aaa;padding:32px 0;font-size:14px;";
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
            datasets: [{
                label: "Jumlah Berita",
                data: values,
                backgroundColor: [
                    "rgba(232,112,10,0.90)",
                    "rgba(232,112,10,0.76)",
                    "rgba(232,112,10,0.62)",
                    "rgba(232,112,10,0.50)",
                    "rgba(232,112,10,0.38)",
                ],
                borderColor:     "transparent",
                borderWidth: 0,
                borderRadius: 6,
                borderSkipped: false,
            }]
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
                    ticks:  { precision: 0, font: { size: 12 }, color: "#888" },
                    grid:   { color: "rgba(0,0,0,0.05)" },
                    border: { display: false },
                },
                y: {
                    ticks: {
                        font:  { size: 14, weight: "600" },
                        color: "#222",
                        crossAlign: "far",
                    },
                    grid: { display: false },
                    border: { display: false },
                },
            },
            layout:          { padding: { right: 20, top: 4, bottom: 4 } },
            barThickness:    15,
            maxBarThickness: 32,
        },
    });
}

// ── Table render ──────────────────────────────────────────────────────────────

function renderTable() {
    const tbody = document.getElementById("tableBody");
    const start = (currentPage - 1) * PER_PAGE;
    const pageData = filteredData.slice(start, start + PER_PAGE);

    if (pageData.length === 0) {
        tbody.innerHTML = `
            <tr class="empty-row"><td colspan="6">
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

    tbody.innerHTML = pageData.map((item, i) => {
        const no = start + i + 1;
        const tags = parseTags(item.tags)
            .map(t => `<span class="tag-chip">#${escapeHtml(t)}</span>`)
            .join(" ");
        const source = escapeHtml(item.source || "—");
        const date = escapeHtml(item.date || "—");
        const internalLink = item.id ? `/berita/${item.id}` : "#";
        const externalLink = escapeHtml(item.url || "#");
        return `
        <tr>
            <td class="td-no">${no}</td>
            <td class="td-judul">${escapeHtml(item.title || "")}</td>
            <td class="td-source">${source}</td>
            <td class="td-date">${date}</td>
            <td class="td-tags">${tags || "—"}</td>
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
    }).join("");

    renderPagination();
}

function parseTags(raw) {
    if (!raw) return [];
    return raw.split(/\s*\|\s*|,\s*/)
        .map(t => t.trim().replace(/^#/, ""))
        .filter(Boolean);
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

// ── Pagination ────────────────────────────────────────────────────────────────

function renderPagination() {
    const container = document.getElementById("pagination");
    const totalPages = Math.ceil(filteredData.length / PER_PAGE);

    if (totalPages <= 1) { container.innerHTML = ""; return; }

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
        if (range[range.length - 1] < totalPages - 1) html += `<span class="page-info">…</span>`;
        html += `<button class="page-btn" onclick="goPage(${totalPages})">${totalPages}</button>`;
    }
    html += `<button class="page-btn" ${currentPage === totalPages ? "disabled" : ""} onclick="goPage(${currentPage + 1})">›</button>`;
    html += `<span class="page-info">${filteredData.length} berita</span>`;

    container.innerHTML = html;
}

function getPageRange(current, total, maxVisible) {
    let start = Math.max(1, current - Math.floor(maxVisible / 2));
    let end = start + maxVisible - 1;
    if (end > total) { end = total; start = Math.max(1, end - maxVisible + 1); }
    const range = [];
    for (let i = start; i <= end; i++) range.push(i);
    return range;
}

function goPage(p) {
    const totalPages = Math.ceil(filteredData.length / PER_PAGE);
    if (p < 1 || p > totalPages) return;
    currentPage = p;
    renderTable();
    document.getElementById("tableSection").scrollIntoView({ behavior: "smooth", block: "start" });
}

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
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

// Debounce helper — tunda panggilan applyFilters agar tidak spam API
let _filterDebounce = null;
function debounceFilters() {
    if (_filterDebounce) clearTimeout(_filterDebounce);
    _filterDebounce = setTimeout(applyFilters, 350);
}

function applyFilters() {
    const search    = (document.getElementById('searchInput').value || '').trim();
    const date_from = document.getElementById('dateFrom').value;   // "yyyy-mm-dd" or ""
    const date_to   = document.getElementById('dateTo').value;

    // Toggle reset button visibility
    const resetBtn = document.getElementById('btnResetDate');
    if (resetBtn) {
        if (date_from || date_to) {
            resetBtn.classList.remove('hidden');
        } else {
            resetBtn.classList.add('hidden');
        }
    }

    // Kirim filter ke server — backend yang filter, bukan client
    loadBerita({ search, date_from, date_to });
}

function resetDateFilter() {
    document.getElementById('dateFrom').value = '';
    document.getElementById('dateTo').value   = '';
    const resetBtn = document.getElementById('btnResetDate');
    if (resetBtn) resetBtn.classList.add('hidden');
    applyFilters();
}

// Keep backward-compat alias
function searchTable(query) {
    const searchInput = document.getElementById('searchInput');
    if (searchInput && query !== undefined) searchInput.value = query;
    applyFilters();
}

// ── Sort ──────────────────────────────────────────────────────────────────────

function applySortDate(arr) {
    arr.sort((a, b) => parseDateID(b.date) - parseDateID(a.date));
}

function sortTable(field) {
    document.querySelectorAll(".th-sortable").forEach(th => th.classList.remove("active"));

    if (sortField === field) {
        sortAsc = !sortAsc;
    } else {
        sortField = field;
        sortAsc = field !== "date";  // date: default desc (terbaru di atas)
    }

    const thEl = document.querySelector(`[onclick="sortTable('${field}')"]`);
    if (thEl) {
        thEl.classList.add("active");
        const icon = document.getElementById(`sort-${field}`);
        if (icon) icon.textContent = sortAsc ? "↑" : "↓";
    }

    filteredData.sort((a, b) => {
        if (field === "date") {
            const diff = parseDateID(a.date) - parseDateID(b.date);
            return sortAsc ? diff : -diff;
        }
        const va = (a[field] || "").toLowerCase();
        const vb = (b[field] || "").toLowerCase();
        if (va < vb) return sortAsc ? -1 : 1;
        if (va > vb) return sortAsc ? 1 : -1;
        return 0;
    });

    currentPage = 1;
    renderTable();
}

// ── Download Excel ────────────────────────────────────────────────────────────

async function downloadExcel() {
    if (allData.length === 0) {
        alert("Belum ada data untuk diunduh.");
        return;
    }

    // Fetch ulang dengan kolom content (tidak ada di tabel biasa)
    let exportData = filteredData;
    try {
        const params = new URLSearchParams();
        // Ambil filter aktif saat ini
        const searchVal   = (document.getElementById('searchInput')?.value || '').trim();
        const date_from   = document.getElementById('dateFrom')?.value || '';
        const date_to     = document.getElementById('dateTo')?.value   || '';
        if (searchVal)  params.set('search',    searchVal);
        if (date_from)  params.set('date_from', date_from);
        if (date_to)    params.set('date_to',   date_to);
        params.set('with_content', '1');

        const res = await fetch("/api/berita/export?" + params.toString());
        if (res.ok) {
            const json = await res.json();
            if (json.status === 'ok') exportData = json.data;
        }
    } catch (e) {
        console.warn("Export fetch gagal, pakai data tabel saja:", e);
    }

    const rows = exportData.map((item, i) => ({
        No:      i + 1,
        Judul:   item.title   || "",
        Sumber:  item.source  || "",
        Tanggal: item.date    || "",
        URL:     item.url     || "",
        Tags:    item.tags    || "",
        Konten:  item.content || "",
    }));

    const ws = XLSX.utils.json_to_sheet(rows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Berita");

    ws["!cols"] = [
        { wch: 5  },   // No
        { wch: 50 },   // Judul
        { wch: 15 },   // Sumber
        { wch: 25 },   // Tanggal
        { wch: 40 },   // URL
        { wch: 30 },   // Tags
        { wch: 80 },   // Konten
    ];

    XLSX.writeFile(wb, "berita_lokal_tegal.xlsx");
}

// ── AI Insights ───────────────────────────────────────────────────────────────

let _aiLoading = false;

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
    q1:     "Triwulan I (Jan–Mar)",
    q2:     "Triwulan II (Apr–Jun)",
    q3:     "Triwulan III (Jul–Sep)",
    q4:     "Triwulan IV (Okt–Des)",
    s1:     "Semester I (Jan–Jun)",
    s2:     "Semester II (Jul–Des)",
    yearly: "Tahunan (Jan–Des)",
};

function _initPeriodDropdown() {
    if (_currentPeriod) return;
    const def = _getDefaultPeriod();
    _currentPeriod = def;
    const label = document.getElementById("aiPeriodLabel");
    if (label) label.textContent = _PERIOD_LABELS[def] || def;
    // Mark active option
    document.querySelectorAll(".ai-period-option").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.value === def);
    });
    // Close menu on outside click
    document.addEventListener("click", e => {
        const dd = document.getElementById("aiPeriodDropdown");
        if (dd && !dd.contains(e.target)) closePeriodDropdown();
    });
}

function togglePeriodDropdown() {
    const menu = document.getElementById("aiPeriodMenu");
    const btn  = document.getElementById("aiPeriodBtn");
    if (!menu) return;
    const isOpen = menu.style.display !== "none";
    menu.style.display = isOpen ? "none" : "";
    btn?.classList.toggle("open", !isOpen);
}

function closePeriodDropdown() {
    const menu = document.getElementById("aiPeriodMenu");
    const btn  = document.getElementById("aiPeriodBtn");
    if (menu) menu.style.display = "none";
    btn?.classList.remove("open");
}

function selectPeriod(value, label) {
    _currentPeriod = value;
    const labelEl = document.getElementById("aiPeriodLabel");
    if (labelEl) labelEl.textContent = label;
    document.querySelectorAll(".ai-period-option").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.value === value);
    });
    closePeriodDropdown();
    loadAIInsights({ forceRefresh: false });
}

function setAILoading(loading, articleCount) {
    _aiLoading = loading;
    const btn        = document.getElementById("btnRefreshAI");
    const statusBar  = document.getElementById("aiLoadingStatus");
    const statusText = document.getElementById("aiLoadingText");
    const refreshTxt = document.getElementById("btnRefreshText");
    const icon       = document.getElementById("refreshIcon");

    if (loading) {
        if (btn)  { btn.classList.add("loading"); btn.disabled = true; }
        if (refreshTxt) refreshTxt.textContent = "Memuat...";
        if (statusBar)  statusBar.style.display = "";
        const n = articleCount ? `${articleCount}` : "";
        if (statusText) statusText.textContent = n
            ? `Menganalisis ${n} berita dengan DeepSeek AI...`
            : "Menganalisis berita dengan DeepSeek AI...";
        // Animasi pulse pada cards
        ["aiCardPdrb", "aiCardKemiskinan", "aiCardPengangguran"].forEach(id => {
            document.getElementById(id)?.classList.add("ai-card-loading");
        });
    } else {
        if (btn)  { btn.classList.remove("loading"); btn.disabled = false; }
        if (refreshTxt) refreshTxt.textContent = "Refresh";
        if (statusBar)  statusBar.style.display = "none";
        ["aiCardPdrb", "aiCardKemiskinan", "aiCardPengangguran"].forEach(id => {
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
    ["aiBodyPdrb", "aiBodyKemiskinan", "aiBodyPengangguran"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = skeletonHtml;
    });
    // Sembunyikan sumber
    ["aiSourcesPdrb", "aiSourcesKemiskinan", "aiSourcesPengangguran"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = "none";
    });
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
    ["aiBodyPdrb", "aiBodyKemiskinan", "aiBodyPengangguran"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = errorHtml;
    });
}

function _renderSources(catKey, sources) {
    // catKey: "Pdrb" | "Kemiskinan" | "Pengangguran"
    const wrap  = document.getElementById(`aiSources${catKey}`);
    const label = document.getElementById(`aiSourcesLabel${catKey}`);
    const list  = document.getElementById(`aiSourcesList${catKey}`);
    if (!wrap || !label || !list) return;

    if (!sources || sources.length === 0) {
        wrap.style.display = "none";
        return;
    }

    label.textContent = `Sumber Berita (${sources.length})`;
    list.innerHTML = sources.map(s => {
        const title = escapeHtml(s.title || "—");
        const url   = escapeHtml(s.url || "#");
        return `<li><a href="${url}" target="_blank" rel="noopener noreferrer">${title}</a></li>`;
    }).join("");
    wrap.style.display = "";
    list.style.display = "none";  // collapsed by default
}

function toggleSources(catKey) {
    const list   = document.getElementById(`aiSourcesList${catKey}`);
    const btn    = document.querySelector(`#aiSources${catKey} .ai-sources-toggle`);
    if (!list) return;
    const isOpen = list.style.display !== "none";
    list.style.display = isOpen ? "none" : "";
    if (btn) btn.classList.toggle("open", !isOpen);
}

function renderAIInsights(json) {
    const { data, article_count: count, quarter, sources = {} } = json;

    // Teks insight
    const categoryMap = {
        aiBodyPdrb:         data?.pdrb         || "—",
        aiBodyKemiskinan:   data?.kemiskinan   || "—",
        aiBodyPengangguran: data?.pengangguran || "—",
    };
    for (const [id, text] of Object.entries(categoryMap)) {
        const el = document.getElementById(id);
        if (el) el.innerHTML = `<p class="ai-insight-text">${escapeHtml(text)}</p>`;
    }

    // Label periode
    const quarterEl = document.getElementById("aiQuarterLabel");
    if (quarterEl) quarterEl.textContent = quarter || "periode ini";

    // Badge jumlah berita
    const countBadge = document.getElementById("aiArticleCount");
    const countText  = document.getElementById("aiArticleCountText");
    if (countBadge && countText) {
        countText.textContent    = `${count} berita dianalisis`;
        countBadge.style.display = count ? "" : "none";
    }

    // Sumber berita per kategori
    _renderSources("Pdrb",         sources.pdrb         || []);
    _renderSources("Kemiskinan",   sources.kemiskinan   || []);
    _renderSources("Pengangguran", sources.pengangguran || []);
}

async function loadAIInsights({ forceRefresh = false, period = "" } = {}) {
    if (_aiLoading) return;

    _initPeriodDropdown();
    const selectedPeriod = period || _currentPeriod || _getDefaultPeriod();

    setAILoading(true);
    _showAISkeleton();

    try {
        const params = new URLSearchParams({ period: selectedPeriod });
        if (forceRefresh) params.set("refresh", "1");
        const url = "/api/ai-insights?" + params.toString();

        const res = await fetch(url);
        if (res.status === 401) { window.location.href = "/login"; return; }
        const json = await res.json();

        if (json.status === "ok") {
            // Update status text dengan jumlah artikel nyata sebelum render
            const statusText = document.getElementById("aiLoadingText");
            if (statusText && json.article_count) {
                statusText.textContent = `Selesai — ${json.article_count} berita dianalisis.`;
            }
            renderAIInsights(json);
        } else {
            _showAIError(json.message || "Gagal memuat insight AI.");
        }
    } catch (err) {
        _showAIError("Gagal menghubungi server. Coba refresh halaman.");
        console.error("AI Insights error:", err);
    } finally {
        setAILoading(false);
    }
}

function refreshAIInsights() {
    loadAIInsights({ forceRefresh: true });
}
