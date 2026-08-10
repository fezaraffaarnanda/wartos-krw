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
    if (_selectedPdrbPengeluaran) {
      params.set("pdrb_pengeluaran_code", _selectedPdrbPengeluaran);
    }
    if (_selectedArchiveStatus) params.set("archive_status", _selectedArchiveStatus);

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

      if (_tablePaginationState.page > _tablePaginationState.total_pages) {
        currentPage = _tablePaginationState.total_pages;
        await loadBerita();
        return;
      }

      currentPage = _tablePaginationState.page;

      renderTable();
    }
  } catch (err) {
    console.error("Gagal memuat berita:", err);
  }
}

function renderTable() {
  const tbody = document.getElementById("tableBody");
  const pageData = filteredData;

  if (pageData.length === 0) {
    const emptyMessage = getArchiveEmptyMessage();
    tbody.innerHTML = `
            <tr class="empty-row"><td colspan="8">
                <div class="empty-state">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#ccc"
                        stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                    </svg>
                    <p>${emptyMessage}</p>
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
      const kbli = renderKbliCell(
        item.kbli || "",
        item.aktivitas_ekonomi || "",
        item.pdrb_pengeluaran || "",
      );
      const titleBadge = item.is_archived
        ? '<span class="article-status-chip archived">Arsip</span>'
        : '<span class="article-status-chip active">Aktif</span>';
      const actions = renderArticleActionButtons(item);
      const internalLink = item.id ? `/berita/${item.id}` : "#";
      const externalLink = escapeHtml(item.url || "#");
      return `
        <tr>
            <td class="td-no">${no}</td>
            <td class="td-judul"><div class="td-judul-stack"><span>${escapeHtml(item.title || "")}</span>${titleBadge}</div></td>
            <td class="td-source">${source}</td>
            <td class="td-date">${date}</td>
            <td class="td-tags">${tags || "—"}</td>
            <td class="td-kbli">${kbli}</td>
            <td class="td-actions">${actions}</td>
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

function applyFilters() {
  const search = (document.getElementById("searchInput").value || "").trim();
  const date_from = document.getElementById("dateFrom").value; // "yyyy-mm-dd" or ""
  const date_to = document.getElementById("dateTo").value;

  _tableFilterState.search = search;
  _tableFilterState.date_from = date_from;
  _tableFilterState.date_to = date_to;
  _tableFilterState.kbli_code = _selectedKbli;
  _tableFilterState.aktivitas_code = _selectedAktivitas;
  _tableFilterState.pdrb_pengeluaran_code = _selectedPdrbPengeluaran;
  _tableFilterState.archive_status = _selectedArchiveStatus;

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
    if (_selectedPdrbPengeluaran) {
      params.set("pdrb_pengeluaran_code", _selectedPdrbPengeluaran);
    }
    if (_selectedArchiveStatus) params.set("archive_status", _selectedArchiveStatus);
    params.set("with_content", "1");

    const res = await fetch("/api/berita/export?" + params.toString());
    if (res.ok) {
      const json = await res.json();
      if (json.status === "ok") exportData = json.data;
    }
  } catch (e) {
    console.warn("Export fetch gagal, pakai data tabel saja:", e);
  }

  if (typeof trackEvent === "function") trackEvent("export_data");

  const rows = exportData.map((item, i) => ({
    No: i + 1,
    Judul: item.title || "",
    Sumber: item.source || "",
    Tanggal: item.date || "",
    URL: item.url || "",
    Tags: item.tags || "",
    KBLI: item.kbli || "",
    "Aktivitas Ekonomi": item.aktivitas_ekonomi || "",
    "PDRB Pengeluaran": item.pdrb_pengeluaran || "",
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
    { wch: 58 }, // PDRB Pengeluaran
    { wch: 80 }, // Konten
  ];

  XLSX.writeFile(wb, "berita_lokal_karawang.xlsx");
}

function renderArticleActionButtons(item) {
  const beritaId = Number(item.id || 0);
  if (!beritaId) return "—";

  const isArchived = Boolean(item.is_archived);
  const archiveLabel = isArchived ? "Pulihkan" : "Arsipkan";
  const archiveToneClass = isArchived ? "secondary" : "warn";

  return `
    <div class="table-action-stack">
      <button
        type="button"
        class="table-action-btn secondary"
        onclick="openArticleEditorById(${beritaId})"
      >Edit</button>
      <button
        type="button"
        class="table-action-btn ${archiveToneClass}"
        onclick="toggleArticleArchive(${beritaId}, ${isArchived ? "false" : "true"})"
      >${archiveLabel}</button>
    </div>
  `;
}

function getArchiveEmptyMessage() {
  if (_selectedArchiveStatus === "archived") {
    return "Belum ada berita yang diarsipkan.";
  }

  if (_selectedArchiveStatus === "all") {
    return 'Belum ada data. Klik <strong>"Scrape Berita"</strong> untuk memulai.';
  }

  return 'Belum ada berita aktif. Klik <strong>"Scrape Berita"</strong> untuk memulai atau buka filter <strong>Arsip</strong>.';
}

function getKbliCode(kbliValue) {
  const raw = String(kbliValue || "").trim();
  if (!raw) return "";
  if (raw.toLowerCase() === "tidak relevan") return "TIDAK RELEVAN";
  const slashIndex = raw.indexOf("/");
  return (slashIndex === -1 ? raw : raw.slice(0, slashIndex)).trim().toUpperCase();
}

function getAktivitasCode(aktivitasValue) {
  const raw = String(aktivitasValue || "").trim();
  if (!raw) return "";
  if (raw === "—") return "—";
  if (raw.toLowerCase() === "tidak relevan") return "Tidak Relevan";
  const slashIndex = raw.indexOf("/");
  return (slashIndex === -1 ? raw : raw.slice(0, slashIndex)).trim();
}

function getPdrbPengeluaranCode(pdrbValue) {
  const raw = String(pdrbValue || "").trim();
  if (!raw) return "";
  if (raw === "—") return "—";
  if (raw.toLowerCase() === "tidak relevan") return "Tidak Relevan";
  const slashIndex = raw.indexOf("/");
  return (slashIndex === -1 ? raw : raw.slice(0, slashIndex)).trim().toUpperCase();
}
