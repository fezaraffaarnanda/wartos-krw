// Halaman kelola masukan pengguna (/admin/feedback).
//
// Admin melihat seluruh masukan, menandai tindak lanjut, dan menghapus yang
// spam. Isi masukan (rating/kategori/komentar) tidak bisa diedit -- itu
// kesaksian pengirim; yang tersimpan dari sisi admin hanya status dan catatan
// internal. Batas yang sama juga ditegakkan di schemas/feedback.py.

const FEEDBACK_PER_PAGE = 20;

const FEEDBACK_CATEGORY_LABELS = {
  berita: "Data Berita",
  ai_chat: "AI Chat",
  ai_insight: "Insight AI",
  statistik_resmi: "Data Official Statistic",
  scraping: "Scraping",
  lainnya: "Lainnya",
};

const FEEDBACK_STATUS_LABELS = {
  baru: "Baru",
  dibaca: "Dibaca",
  ditindaklanjuti: "Ditindaklanjuti",
};

let feedbackState = { page: 1, totalPages: 1, status: "", category: "", rows: [], editingId: null };

document.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("btnRefreshFeedback")?.addEventListener("click", () => loadFeedback(feedbackState.page));
  document.getElementById("btnSendFeedback")?.addEventListener("click", () => openFeedbackModal({ triggerSource: "sidebar" }));

  document.getElementById("feedbackStatusFilter")?.addEventListener("change", (e) => {
    feedbackState.status = e.target.value;
    loadFeedback(1);
  });
  document.getElementById("feedbackCategoryFilter")?.addEventListener("change", (e) => {
    feedbackState.category = e.target.value;
    loadFeedback(1);
  });

  document.getElementById("feedbackTableBody")?.addEventListener("click", onFeedbackRowAction);
  document.getElementById("feedbackPagination")?.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-page]");
    if (btn) loadFeedback(Number(btn.dataset.page));
  });

  document.getElementById("btnCancelFeedbackStatus")?.addEventListener("click", closeStatusModal);
  document.getElementById("btnSaveFeedbackStatus")?.addEventListener("click", saveFeedbackStatus);

  // Overlay loading halaman disembunyikan di finally: kalau request gagal,
  // yang harus terlihat adalah pesan errornya, bukan overlay yang menggantung.
  try {
    await loadFeedback(1);
  } finally {
    if (typeof hidePageLoadingOverlay === "function") hidePageLoadingOverlay();
  }
});

async function loadFeedback(page = 1) {
  const tbody = document.getElementById("feedbackTableBody");
  if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="table-empty">Memuat data masukan...</td></tr>`;

  const params = new URLSearchParams({ page: String(page), per_page: String(FEEDBACK_PER_PAGE) });
  if (feedbackState.status) params.set("status", feedbackState.status);
  if (feedbackState.category) params.set("category", feedbackState.category);

  try {
    const response = await fetch(`/api/admin/feedback?${params.toString()}`);
    if (response.status === 401) { window.location.href = "/login"; return; }
    if (response.status === 403) { window.location.href = "/dashboard"; return; }

    const payload = await response.json();
    if (!response.ok || payload.status !== "ok") {
      if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="table-empty">Gagal memuat masukan.</td></tr>`;
      return;
    }

    feedbackState.page = page;
    feedbackState.totalPages = Number(payload.total_pages || 1);
    feedbackState.rows = payload.data || [];
    renderFeedbackSummary(payload.summary || {});
    renderFeedbackTable(feedbackState.rows, Number(payload.total_items || 0));
    renderFeedbackPagination();
  } catch (_) {
    if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="table-empty">Gagal memuat masukan.</td></tr>`;
  }
}

function renderFeedbackSummary(summary) {
  document.getElementById("feedbackSummaryCount").textContent = summary.count || 0;
  document.getElementById("feedbackSummaryAvg").textContent =
    summary.avg_rating != null ? `${summary.avg_rating} / 5` : "—";
  document.getElementById("feedbackSummaryUnhandled").textContent = summary.unhandled || 0;
}

function renderFeedbackTable(rows, totalItems) {
  const tbody = document.getElementById("feedbackTableBody");
  const countText = document.getElementById("feedbackCountText");
  if (countText) countText.textContent = `${totalItems} masukan`;
  if (!tbody) return;

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="table-empty">Belum ada masukan.</td></tr>`;
    return;
  }

  tbody.innerHTML = rows
    .map((row) => {
      const createdAt = row.created_at
        ? new Date(row.created_at).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" })
        : "—";
      const category = FEEDBACK_CATEGORY_LABELS[row.category] || row.category || "—";
      const status = row.status || "baru";
      const comment = row.comment ? escapeHtml(row.comment) : `<span class="table-empty">—</span>`;
      const note = row.admin_note
        ? `<div class="feedback-admin-note">Catatan: ${escapeHtml(row.admin_note)}</div>`
        : "";
      return `
        <tr>
          <td>${escapeHtml(createdAt)}</td>
          <td>${escapeHtml(row.username || "—")}</td>
          <td class="feedback-rating-badge">${"★".repeat(row.rating || 0)}${"☆".repeat(5 - (row.rating || 0))}</td>
          <td>${escapeHtml(category)}</td>
          <td>${comment}${note}</td>
          <td><span class="feedback-status-pill ${escapeAttr(status)}">${escapeHtml(FEEDBACK_STATUS_LABELS[status] || status)}</span></td>
          <td class="feedback-actions-cell">
            <button type="button" class="btn-mini" data-feedback-action="status" data-id="${row.id}">Tindak Lanjut</button>
            <button type="button" class="btn-mini danger" data-feedback-action="delete" data-id="${row.id}">Hapus</button>
          </td>
        </tr>
      `;
    })
    .join("");
}

function renderFeedbackPagination() {
  const wrap = document.getElementById("feedbackPagination");
  if (!wrap) return;
  const { page, totalPages } = feedbackState;
  if (totalPages <= 1) { wrap.innerHTML = ""; return; }
  wrap.innerHTML = `
    <button type="button" class="btn-mini" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>‹</button>
    <span>Hal. ${page} / ${totalPages}</span>
    <button type="button" class="btn-mini" data-page="${page + 1}" ${page >= totalPages ? "disabled" : ""}>›</button>
  `;
}

function onFeedbackRowAction(event) {
  const btn = event.target.closest("button[data-feedback-action]");
  if (!btn) return;
  const id = Number(btn.dataset.id);
  if (btn.dataset.feedbackAction === "status") openStatusModal(id);
  else if (btn.dataset.feedbackAction === "delete") deleteFeedback(id);
}

// ── Tindak lanjut ─────────────────────────────────────────────────────────

function openStatusModal(id) {
  const row = feedbackState.rows.find((r) => r.id === id);
  if (!row) return;
  feedbackState.editingId = id;

  const createdAt = row.created_at
    ? new Date(row.created_at).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" })
    : "—";
  document.getElementById("feedbackStatusModalMeta").textContent =
    `${row.username || "—"} · ${createdAt} · ${FEEDBACK_CATEGORY_LABELS[row.category] || row.category || "—"}`;
  document.getElementById("feedbackStatusModalComment").textContent = row.comment || "(tanpa komentar)";
  document.getElementById("feedbackStatusSelect").value = row.status || "baru";
  document.getElementById("feedbackAdminNote").value = row.admin_note || "";
  document.getElementById("feedbackStatusModal").classList.add("open");
}

function closeStatusModal() {
  feedbackState.editingId = null;
  document.getElementById("feedbackStatusModal")?.classList.remove("open");
}

async function saveFeedbackStatus() {
  const id = feedbackState.editingId;
  if (id === null) return;
  const btn = document.getElementById("btnSaveFeedbackStatus");
  const body = {
    status: document.getElementById("feedbackStatusSelect").value,
    admin_note: document.getElementById("feedbackAdminNote").value,
  };

  btn.disabled = true;
  try {
    const res = await fetch(`/api/admin/feedback/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data.status !== "ok") { showToast(data.message || "Gagal menyimpan.", "error"); return; }
    showToast("Tindak lanjut tersimpan.", "success");
    closeStatusModal();
    loadFeedback(feedbackState.page);
  } catch (_) {
    showToast("Gagal terhubung ke server.", "error");
  } finally {
    btn.disabled = false;
  }
}

async function deleteFeedback(id) {
  const row = feedbackState.rows.find((r) => r.id === id);
  const confirmed = await showDialog({
    title: "Hapus masukan ini?",
    message: `Masukan dari ${row?.username || "pengguna"} akan dihapus permanen dan tidak bisa dikembalikan.`,
    confirmText: "Ya, Hapus",
    cancelText: "Batal",
    showCancel: true,
    danger: true,
  });
  if (!confirmed) return;

  try {
    const res = await fetch(`/api/admin/feedback/${id}`, { method: "DELETE" });
    const data = await res.json();
    if (data.status !== "ok") { showToast(data.message || "Gagal menghapus.", "error"); return; }
    showToast("Masukan dihapus.", "success");
    // Halaman terakhir bisa jadi kosong setelah baris terakhirnya hilang.
    const nextPage = feedbackState.rows.length === 1 && feedbackState.page > 1
      ? feedbackState.page - 1
      : feedbackState.page;
    loadFeedback(nextPage);
  } catch (_) {
    showToast("Gagal terhubung ke server.", "error");
  }
}
