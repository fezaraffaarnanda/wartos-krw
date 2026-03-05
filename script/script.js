/* ============================================
   Dashboard Berita RadarTegal — Frontend Logic
   ============================================ */

let allData = [];
let filteredData = [];
let currentPage = 1;
const PER_PAGE = 15;
let sortField = null;
let sortAsc = true;
let chartInstance = null;

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
    updateTimestamp();
    loadBerita();
    animateCards();
});

function updateTimestamp() {
    const el = document.getElementById("headerTimestamp");
    const now = new Date();
    el.textContent = now.toLocaleDateString("id-ID", {
        weekday: "long", year: "numeric", month: "long", day: "numeric",
        hour: "2-digit", minute: "2-digit"
    });
}

function animateCards() {
    document.querySelectorAll(".card-animate").forEach((card, i) => {
        setTimeout(() => card.classList.add("visible"), 100 + i * 80);
    });
}

// ── Load berita dari API ─────────────────────────────────────────────────────

async function loadBerita() {
    try {
        const res = await fetch("/api/berita");
        const json = await res.json();
        if (json.status === "ok") {
            allData = json.data || [];
            filteredData = [...allData];
            currentPage = 1;
            updateSummary();
            renderTable();
            renderChart();
        }
    } catch (err) {
        console.error("Gagal memuat berita:", err);
    }
}

// ── Scrape berita baru ──────────────────────────────────────────────────────

async function scrapeBerita() {
    const btn = document.getElementById("btnScrape");
    btn.classList.add("loading");
    btn.disabled = true;

    const maxPagesInput = document.getElementById("maxPages");
    const maxPages = maxPagesInput.value ? parseInt(maxPagesInput.value) : null;

    try {
        const res = await fetch("/api/scrape", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ max_pages: maxPages }),
        });
        const json = await res.json();

        if (json.status === "ok") {
            alert(`Scraping selesai. ${json.count} berita baru disimpan.`);
            await loadBerita();
        } else {
            alert("Error: " + json.message);
        }
    } catch (err) {
        alert("Gagal menjalankan scraping: " + err.message);
    } finally {
        btn.classList.remove("loading");
        btn.disabled = false;
    }
}

// ── Summary cards ─────────────────────────────────────────────────────────────

function updateSummary() {
    document.getElementById("totalBerita").textContent = allData.length;

    const tagCount = {};
    allData.forEach(item => {
        if (!item.tags) return;
        item.tags.split(" | ").forEach(t => {
            const tag = t.trim();
            if (tag) tagCount[tag] = (tagCount[tag] || 0) + 1;
        });
    });

    const uniqueTags = Object.keys(tagCount).length;
    document.getElementById("totalTags").textContent = uniqueTags;

    const sorted = Object.entries(tagCount).sort((a, b) => b[1] - a[1]);
    const topEl = document.getElementById("topTag");
    if (sorted.length > 0) {
        topEl.textContent = sorted[0][0];
        topEl.classList.add("text-value");
    } else {
        topEl.textContent = "—";
    }

    const latestEl = document.getElementById("tanggalTerbaru");
    if (allData.length > 0 && allData[0].date) {
        latestEl.textContent = allData[0].date;
    } else {
        latestEl.textContent = "—";
    }
}

// ── Chart ────────────────────────────────────────────────────────────────────

function renderChart() {
    const tagCount = {};
    allData.forEach(item => {
        if (!item.tags) return;
        item.tags.split(" | ").forEach(t => {
            const tag = t.trim();
            if (tag) tagCount[tag] = (tagCount[tag] || 0) + 1;
        });
    });

    const sorted = Object.entries(tagCount)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 15);

    const labels = sorted.map(e => e[0]);
    const values = sorted.map(e => e[1]);

    const canvas = document.getElementById("chartTags");
    if (!canvas) return;

    if (chartInstance) chartInstance.destroy();

    chartInstance = new Chart(canvas, {
        type: "bar",
        data: {
            labels,
            datasets: [{
                label: "Jumlah Berita",
                data: values,
                backgroundColor: "rgba(232, 112, 10, 0.75)",
                borderColor: "rgba(232, 112, 10, 1)",
                borderWidth: 1,
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: "y",
            plugins: {
                legend: { display: false },
            },
            scales: {
                x: {
                    beginAtZero: true,
                    ticks: { precision: 0 },
                    grid: { color: "rgba(0,0,0,0.05)" },
                },
                y: {
                    ticks: { font: { size: 12 } },
                    grid: { display: false },
                },
            },
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
            <tr class="empty-row"><td colspan="5">
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
        const tags = (item.tags || "").split(" | ").filter(Boolean)
            .map(t => `<span class="kategori-badge">${escapeHtml(t)}</span>`)
            .join(" ");
        return `
        <tr>
            <td class="td-no">${no}</td>
            <td class="td-judul">${escapeHtml(item.title || "")}</td>
            <td class="td-sumber">${escapeHtml(item.date || "")}</td>
            <td class="td-kategori">${tags || "—"}</td>
            <td class="td-link">
                <a href="${escapeHtml(item.url || "#")}" target="_blank" class="link-btn">Buka</a>
            </td>
        </tr>`;
    }).join("");

    renderPagination();
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

    if (totalPages <= 1) {
        container.innerHTML = "";
        return;
    }

    let html = "";

    html += `<button class="page-btn" ${currentPage === 1 ? "disabled" : ""} onclick="goPage(${currentPage - 1})">‹</button>`;

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
    if (end > total) {
        end = total;
        start = Math.max(1, end - maxVisible + 1);
    }
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

// ── Search ────────────────────────────────────────────────────────────────────

function searchTable(query) {
    const q = query.toLowerCase().trim();
    if (!q) {
        filteredData = [...allData];
    } else {
        filteredData = allData.filter(item =>
            (item.title || "").toLowerCase().includes(q) ||
            (item.date || "").toLowerCase().includes(q) ||
            (item.tags || "").toLowerCase().includes(q)
        );
    }
    currentPage = 1;
    renderTable();
}

// ── Sort ──────────────────────────────────────────────────────────────────────

function sortTable(field) {
    document.querySelectorAll(".th-sortable").forEach(th => th.classList.remove("active"));

    if (sortField === field) {
        sortAsc = !sortAsc;
    } else {
        sortField = field;
        sortAsc = true;
    }

    const thEl = document.querySelector(`[onclick="sortTable('${field}')"]`);
    if (thEl) {
        thEl.classList.add("active");
        const icon = document.getElementById(`sort-${field}`);
        if (icon) icon.textContent = sortAsc ? "↑" : "↓";
    }

    filteredData.sort((a, b) => {
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

function downloadExcel() {
    if (allData.length === 0) {
        alert("Belum ada data untuk diunduh.");
        return;
    }

    const rows = allData.map((item, i) => ({
        No: i + 1,
        Judul: item.title || "",
        Tanggal: item.date || "",
        URL: item.url || "",
        Tags: item.tags || "",
        Konten: item.content || "",
    }));

    const ws = XLSX.utils.json_to_sheet(rows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Berita");

    const colWidths = [
        { wch: 5 },   // No
        { wch: 50 },  // Judul
        { wch: 25 },  // Tanggal
        { wch: 40 },  // URL
        { wch: 30 },  // Tags
        { wch: 80 },  // Konten
    ];
    ws["!cols"] = colWidths;

    XLSX.writeFile(wb, "berita_radartegal.xlsx");
}
