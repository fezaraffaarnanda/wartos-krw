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

function startRealtimeClock() {
  updateTimestamp();
  if (clockTimer) clearInterval(clockTimer);
  clockTimer = setInterval(updateTimestamp, 1000);
}

// ── Auto-refresh (tiap 5 menit) ───────────────────────────────────────────────
// Biar last scrape & data tabel otomatis update kalau cron baru saja jalan.

function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(async () => {
    // Jangan refresh kalau sedang ada polling scraping manual
    if (pollTimer) return;
    const tasks = [loadLastScrape(), loadOverviewSummary()];
    // Tabel berita hanya ikut di-refresh kalau tab Data memang sudah pernah
    // dibuka — kalau belum, jangan tarik /api/berita sia-sia.
    if (_beritaLoaded && !_beritaLoading) tasks.push(loadBerita());
    await Promise.all(tasks);
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

// loadUserInfo di-cache di level promise supaya pemanggil kedua (mis.
// initFeedbackWidget di shared/feedback.js) reuse hasilnya, bukan hit
// /api/me untuk kedua kalinya saat load awal.
let _userInfoPromise = null;

function loadUserInfo() {
  if (!_userInfoPromise) _userInfoPromise = _fetchUserInfo();
  return _userInfoPromise;
}

// Dipublikasikan dengan nama unik supaya shared/feedback.js bisa ikut memakai
// cache ini hanya di dashboard, tanpa bentrok dengan loadUserInfo() milik
// halaman lain (mis. static/js/berita/detail.js).
window.getCachedUserInfo = loadUserInfo;

async function _fetchUserInfo() {
  try {
    const res = await fetch("/api/me");
    if (res.status === 401) {
      window.location.href = "/login";
      return null;
    }
    const json = await res.json();
    if (json.status === "ok") {
      if (json.must_change_password) {
        window.location.href = "/change-password";
        return null;
      }

      currentUser = json;
      const userEl = document.getElementById("headerUser");
      if (userEl) userEl.textContent = json.username;
      const adminUsersLink = document.getElementById("adminUsersLink");
      const adminRelevanceLink = document.getElementById("adminRelevanceLink");
      const adminLlmLink = document.getElementById("adminLlmLink");
      const scrapeNavLink = document.getElementById("scrapeNavLink");
      const guideUserCard = document.getElementById("guideUserCard");
      const guideAdminCard = document.getElementById("guideAdminCard");

      // Info ringkasan scraping tetap tampil di overview untuk semua role.
      // Non-admin hanya tidak mendapat akses ke scrape section.
      if (json.role === "admin") {
        if (adminUsersLink) adminUsersLink.style.display = "inline-flex";
        if (adminRelevanceLink) adminRelevanceLink.style.display = "inline-flex";
        if (adminLlmLink) adminLlmLink.style.display = "inline-flex";
        if (scrapeNavLink) scrapeNavLink.style.display = "inline-flex";
        if (guideAdminCard) guideAdminCard.style.display = "block";
        if (guideUserCard) guideUserCard.style.display = "none";
      } else {
        const scrapeSection = document.getElementById("scrapeSection");
        if (scrapeSection) scrapeSection.style.display = "none";
        if (adminUsersLink) adminUsersLink.style.display = "none";
        if (adminRelevanceLink) adminRelevanceLink.style.display = "none";
        if (adminLlmLink) adminLlmLink.style.display = "none";
        if (scrapeNavLink) scrapeNavLink.style.display = "none";
        if (guideUserCard) guideUserCard.style.display = "block";
        if (guideAdminCard) guideAdminCard.style.display = "none";

        if (_activeView === "scrape") {
          _openView("overview", { updateHash: true });
        }
      }
    }
    return json;
  } catch (e) {
    console.error("Gagal memuat info user:", e);
    return null;
  }
}

function animateCards() {
  document.querySelectorAll(".card-animate").forEach((card, i) => {
    setTimeout(() => card.classList.add("visible"), 100 + i * 80);
  });
}

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
