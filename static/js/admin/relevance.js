// Audit Classifier Relevance — antrian review, label, re-classify, sampel
// audit, metrik, dan siklus hidup prompt. Ditulis ulang dari 254 baris inline
// lama di templates/admin_relevance.html.

const REL_PER_PAGE = 25;
const REL_TABS = [
  { mode: "uncertainty", label: "Prioritas" },
  { mode: "audit", label: "Sampel Audit" },
  { mode: "failed", label: "Gagal Diklasifikasi" },
  { mode: "labeled", label: "Berlabel" },
  { mode: "disagreement", label: "Beda Pendapat" },
  { mode: "all", label: "Semua" },
];
const PROMPT_APPLY_CONFIRMATION = "yes, update system prompt";

// ── State ─────────────────────────────────────────────────────────────────

let relState = {
  mode: "uncertainty",
  page: 1,
  totalPages: 1,
  totalItems: 0,
  search: "",
  source: "",
  rows: [],
  selectedId: null,
  selectedIndex: -1,
  checkedIds: new Set(),
  itemCache: new Map(), // id -> detail row
  undoing: false,
};

let relDraft = { current: null, draft: null, evalResult: null };

// ── Init ──────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  initRelevanceGuide();
  bindRelTabs();
  bindRelToolbar();
  bindRelDetailActions();
  bindRelModals();
  bindRelKeyboard();
  loadRelMetrics();
  loadRelQueue(1);
  loadFailedBadge();
  loadAuditBadge();
});

// ── Tabs & toolbar ────────────────────────────────────────────────────────

function bindRelTabs() {
  const wrap = document.getElementById("relTabs");
  if (!wrap) return;
  wrap.addEventListener("click", (e) => {
    const btn = e.target.closest(".rel-tab");
    if (!btn) return;
    wrap.querySelectorAll(".rel-tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    relState.mode = btn.dataset.mode;
    relState.checkedIds.clear();
    setRelTabHint(relState.mode);
    loadRelQueue(1);
  });
}

function bindRelToolbar() {
  const search = document.getElementById("relSearch");
  const source = document.getElementById("relSourceFilter");
  let debounceTimer = null;

  search?.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      relState.search = search.value.trim();
      loadRelQueue(1);
    }, 350);
  });

  source?.addEventListener("change", () => {
    relState.source = source.value;
    loadRelQueue(1);
  });

  document.getElementById("btnRefreshRel")?.addEventListener("click", () => {
    loadRelMetrics();
    loadRelQueue(relState.page);
  });

  document.getElementById("btnDrawAuditSample")?.addEventListener("click", drawAuditSample);
  document.getElementById("btnExportFewShot")?.addEventListener("click", openFewShotExport);
  document.getElementById("btnManagePrompt")?.addEventListener("click", openPromptModal);
  document.getElementById("btnBulkLabelRelevan")?.addEventListener("click", () => bulkLabel(true));
  document.getElementById("btnBulkLabelTidak")?.addEventListener("click", () => bulkLabel(false));
  document.getElementById("btnBulkReclassify")?.addEventListener("click", bulkReclassify);
}

// ── Queue ─────────────────────────────────────────────────────────────────

async function loadRelQueue(page = 1) {
  relState.page = page;
  const body = document.getElementById("relQueueBody");
  if (body) body.innerHTML = `<div class="rel-detail-empty">Memuat...</div>`;

  const params = new URLSearchParams({
    mode: relState.mode,
    page: String(page),
    per_page: String(REL_PER_PAGE),
  });
  if (relState.search) params.set("search", relState.search);
  if (relState.source) params.set("source", relState.source);

  try {
    const res = await fetch(`/api/admin/relevance/review-queue?${params.toString()}`);
    if (res.status === 401) { window.location.href = "/login"; return; }
    const data = await res.json();
    if (data.status !== "ok") {
      if (body) body.innerHTML = `<div class="rel-detail-empty">${escapeHtml(data.message || "Gagal memuat.")}</div>`;
      return;
    }

    relState.rows = data.data || [];
    relState.totalPages = Number(data.total_pages || 1);
    relState.totalItems = Number(data.total_items || 0);
    renderRelQueue();
    renderRelPagination();

    if (relState.rows.length && relState.mode === "audit") {
      loadAuditBadge();
    }

    if (relState.rows.length) {
      selectRelItem(relState.rows[0].id, 0);
      prefetchNextItems(0);
    } else {
      relState.selectedId = null;
      renderRelDetailEmpty("Tidak ada item di antrian ini.");
    }
  } catch (err) {
    if (body) body.innerHTML = `<div class="rel-detail-empty">Gagal terhubung ke server.</div>`;
    console.error(err);
  }
}

function renderRelQueue() {
  const body = document.getElementById("relQueueBody");
  if (!body) return;
  if (!relState.rows.length) {
    body.innerHTML = `<div class="rel-detail-empty">Tidak ada data.</div>`;
    return;
  }
  const bulkAllowed = relState.mode !== "audit";
  body.innerHTML = relState.rows
    .map((row, idx) => {
      const checked = relState.checkedIds.has(row.id);
      return `
      <div class="rel-queue-item${row.id === relState.selectedId ? " selected" : ""}" data-id="${row.id}" data-idx="${idx}">
        ${bulkAllowed ? `<input type="checkbox" data-check-id="${row.id}" ${checked ? "checked" : ""} aria-label="Pilih untuk aksi massal" />` : ""}
        <div class="rel-queue-item-body">
          <div class="rel-queue-item-title">${escapeHtml(row.title || "(tanpa judul)")}</div>
          <div class="rel-queue-item-meta">
            <span class="rel-score-chip">${row.relevance_score ?? "—"}</span>
            ${relPill(row.is_relevant)}
            ${row.human_label !== null && row.human_label !== undefined ? relPill(row.human_label) : ""}
            <span>${escapeHtml(row.source || "")}</span>
          </div>
        </div>
      </div>`;
    })
    .join("");

  body.querySelectorAll(".rel-queue-item").forEach((el) => {
    el.addEventListener("click", (e) => {
      if (e.target.matches("input[type=checkbox]")) return;
      selectRelItem(Number(el.dataset.id), Number(el.dataset.idx));
    });
  });
  body.querySelectorAll("input[data-check-id]").forEach((cb) => {
    cb.addEventListener("change", () => {
      const id = Number(cb.dataset.checkId);
      if (cb.checked) relState.checkedIds.add(id);
      else relState.checkedIds.delete(id);
      renderBulkBar();
    });
  });
  renderBulkBar();
}

function relPill(val) {
  if (val === true) return '<span class="rel-pill yes">Relevan</span>';
  if (val === false) return '<span class="rel-pill no">Tidak</span>';
  return '<span class="rel-pill na">—</span>';
}

function renderRelPagination() {
  const container = document.getElementById("relPagination");
  if (!container) return;
  if (relState.totalPages <= 1) {
    container.innerHTML = `<span class="page-info">${relState.totalItems} item</span>`;
    return;
  }
  const cur = relState.page;
  const total = relState.totalPages;
  let start = Math.max(1, cur - 2);
  const end = Math.min(total, start + 4);
  start = Math.max(1, end - 4);

  let html = `<button class="page-btn" ${cur === 1 ? "disabled" : ""} onclick="loadRelQueue(${cur - 1})">‹</button>`;
  if (start > 1) {
    html += `<button class="page-btn" onclick="loadRelQueue(1)">1</button>`;
    if (start > 2) html += `<span class="page-info">…</span>`;
  }
  for (let p = start; p <= end; p++) {
    html += `<button class="page-btn ${p === cur ? "active" : ""}" onclick="loadRelQueue(${p})">${p}</button>`;
  }
  if (end < total) {
    if (end < total - 1) html += `<span class="page-info">…</span>`;
    html += `<button class="page-btn" onclick="loadRelQueue(${total})">${total}</button>`;
  }
  html += `<button class="page-btn" ${cur === total ? "disabled" : ""} onclick="loadRelQueue(${cur + 1})">›</button>`;
  html += `<span class="page-info">${relState.totalItems} item</span>`;
  container.innerHTML = html;
}

function renderBulkBar() {
  const bar = document.getElementById("relBulkBar");
  if (!bar) return;
  const n = relState.checkedIds.size;
  bar.style.display = n > 0 ? "flex" : "none";
  const countEl = document.getElementById("relBulkCount");
  if (countEl) countEl.textContent = `${n} dipilih`;
}

// ── Detail panel ──────────────────────────────────────────────────────────

async function fetchRelItem(id) {
  if (relState.itemCache.has(id)) return relState.itemCache.get(id);
  const res = await fetch(`/api/admin/relevance/item/${id}`);
  if (res.status === 401) { window.location.href = "/login"; return null; }
  const data = await res.json();
  if (data.status !== "ok") return null;
  relState.itemCache.set(id, data.data);
  return data.data;
}

function prefetchNextItems(fromIdx) {
  const targets = relState.rows.slice(fromIdx + 1, fromIdx + 3);
  targets.forEach((row) => {
    if (!relState.itemCache.has(row.id)) fetchRelItem(row.id);
  });
}

async function selectRelItem(id, idx) {
  relState.selectedId = id;
  relState.selectedIndex = idx;
  document.querySelectorAll(".rel-queue-item").forEach((el) => {
    el.classList.toggle("selected", Number(el.dataset.id) === id);
  });

  const detail = document.getElementById("relDetail");
  if (detail) detail.innerHTML = `<div class="rel-detail-empty">Memuat detail...</div>`;

  const item = await fetchRelItem(id);
  if (!item) {
    renderRelDetailEmpty("Gagal memuat detail item.");
    return;
  }
  renderRelDetail(item);
  prefetchNextItems(idx);
}

function renderRelDetailEmpty(message) {
  const detail = document.getElementById("relDetail");
  if (detail) detail.innerHTML = `<div class="rel-detail-empty">${escapeHtml(message)}</div>`;
}

function renderRelDetail(item) {
  const detail = document.getElementById("relDetail");
  if (!detail) return;
  const tags = parseTags(item.tags).slice(0, 12);

  detail.innerHTML = `
    <div class="rel-detail-head">
      <h3>${escapeHtml(item.title || "(tanpa judul)")}</h3>
      <div class="rel-detail-head-meta">
        <span>${escapeHtml(item.source || "—")}</span>
        <span>${escapeHtml(item.date_parsed || "—")}</span>
        ${item.url ? `<a href="${escapeAttr(item.url)}" target="_blank" rel="noopener">Buka Asli ↗</a>` : ""}
      </div>
      ${tags.length ? `<div class="rel-detail-tags">${tags.map((t) => `<span class="tag-chip">#${escapeHtml(t)}</span>`).join("")}</div>` : ""}
    </div>

    <div class="rel-detail-verdict">
      <div class="rel-verdict-panel">
        <h4>Mesin</h4>
        <p>Skor: <strong>${item.relevance_score ?? "—"}</strong> ${relPill(item.is_relevant)}</p>
        <p>${escapeHtml(item.relevance_reason || "—")}</p>
        <p>Versi: ${escapeHtml(item.relevance_prompt_version || "—")} · Dicek: ${escapeHtml(item.relevance_checked_at || "belum pernah")}</p>
      </div>
      <div class="rel-verdict-panel">
        <h4>Manusia</h4>
        <p>${relPill(item.human_label)} ${item.human_labeled_by ? `oleh ${escapeHtml(item.human_labeled_by)}` : ""}</p>
        <p>${escapeHtml(item.human_labeled_at || "belum dilabeli")}</p>
        ${item.human_label_note ? `<p>Catatan: ${escapeHtml(item.human_label_note)}</p>` : ""}
      </div>
    </div>

    <div class="rel-detail-body">${escapeHtml(item.content || "(tidak ada konten)")}</div>

    <div class="rel-detail-actions">
      <button class="btn-admin" type="button" data-action="relevan"><kbd class="rel-key">R</kbd> Relevan</button>
      <button class="btn-admin ghost" type="button" data-action="tidak"><kbd class="rel-key">T</kbd> Tidak Relevan</button>
      <button class="btn-admin ghost" type="button" data-action="lewati"><kbd class="rel-key">S</kbd> Lewati</button>
      <button class="btn-admin ghost" type="button" data-action="undo"><kbd class="rel-key">U</kbd> Batalkan Label</button>
      <button class="btn-admin ghost" type="button" data-action="reclassify"><kbd class="rel-key">C</kbd> Klasifikasi Ulang</button>
    </div>
    <div class="rel-detail-note">
      <textarea id="relNoteInput" placeholder="Catatan label (opsional, tekan N untuk fokus di sini)">${escapeHtml(item.human_label_note || "")}</textarea>
    </div>
  `;
}

function bindRelDetailActions() {
  document.getElementById("relDetail")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    const action = btn.dataset.action;
    if (action === "relevan") labelCurrent(true);
    else if (action === "tidak") labelCurrent(false);
    else if (action === "lewati") advanceToNext();
    else if (action === "undo") undoLastLabel();
    else if (action === "reclassify") reclassifyCurrent();
  });
}

// ── Label actions ─────────────────────────────────────────────────────────

async function labelCurrent(isRelevant) {
  if (relState.selectedId === null) return;
  const id = relState.selectedId;
  const labelSource = relState.mode === "audit" ? "audit" : "targeted";
  const note = document.getElementById("relNoteInput")?.value || "";

  // Optimistic UI: perbarui pill di list dulu, baru kirim request.
  const row = relState.rows.find((r) => r.id === id);
  if (row) row.human_label = isRelevant;
  renderRelQueue();

  try {
    const res = await fetch(`/api/admin/berita/${id}/human-label`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_relevant: isRelevant, label_source: labelSource, note }),
    });
    const data = await res.json();
    if (data.status !== "ok") {
      showToast(data.message || "Gagal menyimpan label.", "error");
      if (row) row.human_label = null;
      renderRelQueue();
      return;
    }
    relState.itemCache.delete(id);
    if (relState.mode === "audit") loadAuditBadge();
    loadRelMetrics();
    advanceToNext();
  } catch (err) {
    showToast("Gagal terhubung ke server.", "error");
    if (row) row.human_label = null;
    renderRelQueue();
  }
}

async function undoLastLabel() {
  if (relState.undoing) return;
  relState.undoing = true;
  try {
    const res = await fetch("/api/admin/relevance/undo", { method: "POST" });
    const data = await res.json();
    if (data.status !== "ok") {
      showToast(data.message || "Tidak ada label untuk dibatalkan.", "warning");
      return;
    }
    showToast("Label dibatalkan.", "success", 2500);
    relState.itemCache.delete(data.data.berita_id);
    loadRelMetrics();
    loadRelQueue(relState.page);
  } catch (err) {
    showToast("Gagal terhubung ke server.", "error");
  } finally {
    relState.undoing = false;
  }
}

function advanceToNext() {
  const nextIdx = relState.selectedIndex + 1;
  if (nextIdx < relState.rows.length) {
    selectRelItem(relState.rows[nextIdx].id, nextIdx);
  } else if (relState.page < relState.totalPages) {
    loadRelQueue(relState.page + 1);
  } else {
    renderRelDetailEmpty("Antrean di halaman ini selesai.");
  }
}

async function bulkLabel(isRelevant) {
  const ids = Array.from(relState.checkedIds);
  if (!ids.length) return;
  const confirmed = await showDialog({
    title: `Label ${ids.length} item sebagai ${isRelevant ? "Relevan" : "Tidak Relevan"}?`,
    message: "Aksi ini langsung tersimpan dan tercatat di riwayat label.",
    confirmText: "Ya, Label Massal",
    cancelText: "Batal",
    showCancel: true,
  });
  if (!confirmed) return;

  try {
    const res = await fetch("/api/admin/relevance/bulk-label", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ berita_ids: ids, is_relevant: isRelevant, label_source: "targeted" }),
    });
    const data = await res.json();
    if (data.status !== "ok") { showToast(data.message || "Gagal label massal.", "error"); return; }
    showToast(`${data.updated} item dilabel, ${data.failed.length} gagal.`, "success");
    relState.checkedIds.clear();
    relState.itemCache.clear();
    loadRelMetrics();
    loadRelQueue(relState.page);
  } catch (err) {
    showToast("Gagal terhubung ke server.", "error");
  }
}

// ── Reclassify ────────────────────────────────────────────────────────────

async function reclassifyCurrent() {
  if (relState.selectedId === null) return;
  const id = relState.selectedId;
  showToast("Mengklasifikasi ulang...", "info", 2000);
  try {
    const res = await fetch(`/api/admin/berita/${id}/reclassify`, { method: "POST" });
    const data = await res.json();
    if (data.status !== "ok") { showToast(data.message || "Gagal klasifikasi ulang.", "error"); return; }
    showToast(`Skor baru: ${data.data.relevance_score} (${data.data.is_relevant ? "Relevan" : "Tidak Relevan"})`, "success");
    relState.itemCache.delete(id);
    loadRelMetrics();
    if (relState.mode === "failed") loadRelQueue(relState.page);
    else selectRelItem(id, relState.selectedIndex);
    loadFailedBadge();
  } catch (err) {
    showToast("Gagal terhubung ke server.", "error");
  }
}

async function bulkReclassify() {
  const ids = Array.from(relState.checkedIds);
  const usingSelection = ids.length > 0;
  const confirmed = await showDialog({
    title: usingSelection ? `Klasifikasi ulang ${ids.length} item?` : "Klasifikasi ulang antrean Gagal Diklasifikasi?",
    message: usingSelection
      ? "Item yang dipilih akan diklasifikasi ulang, mengabaikan batas percobaan otomatis."
      : "Sampai 25 item pertama di antrean Gagal Diklasifikasi akan dicoba ulang.",
    confirmText: "Ya, Proses",
    cancelText: "Batal",
    showCancel: true,
  });
  if (!confirmed) return;

  try {
    const res = await fetch("/api/admin/relevance/reclassify-bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(usingSelection ? { berita_ids: ids } : {}),
    });
    const data = await res.json();
    if (data.status !== "ok") { showToast(data.message || "Gagal klasifikasi ulang massal.", "error"); return; }
    showToast(`${data.succeeded}/${data.requested} berhasil diklasifikasi ulang.`, "success");
    relState.checkedIds.clear();
    relState.itemCache.clear();
    loadRelMetrics();
    loadRelQueue(relState.page);
    loadFailedBadge();
  } catch (err) {
    showToast("Gagal terhubung ke server.", "error");
  }
}

// ── Badge count (Gagal Diklasifikasi, Sampel Audit) ──────────────────────

async function loadFailedBadge() {
  try {
    const res = await fetch("/api/admin/relevance/review-queue?mode=failed&per_page=1");
    const data = await res.json();
    if (data.status !== "ok") return;
    const tab = document.querySelector('.rel-tab[data-mode="failed"]');
    if (tab) tab.textContent = `Gagal Diklasifikasi (${data.total_items})`;
  } catch (err) { /* non-kritis */ }
}

async function loadAuditBadge() {
  try {
    const res = await fetch("/api/admin/relevance/audit-sample");
    const data = await res.json();
    const tab = document.querySelector('.rel-tab[data-mode="audit"]');
    if (!tab) return;
    if (data.status === "ok" && data.progress) {
      tab.textContent = `Sampel Audit (${data.progress.labeled}/${data.progress.total})`;
    } else {
      tab.textContent = "Sampel Audit";
    }
  } catch (err) { /* non-kritis */ }
}

async function drawAuditSample() {
  const confirmed = await showDialog({
    title: "Tarik Sampel Audit Baru?",
    message: "Menarik sampel acak berstrata (20 item/band skor = 100 item) untuk estimasi akurasi tak bias.",
    confirmText: "Ya, Tarik Sampel",
    cancelText: "Batal",
    showCancel: true,
  });
  if (!confirmed) return;

  try {
    const res = await fetch("/api/admin/relevance/audit-sample", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ per_band: 20 }),
    });
    const data = await res.json();
    if (data.status !== "ok") { showToast(data.message || "Gagal menarik sampel.", "error"); return; }
    showToast("Sampel audit baru berhasil ditarik.", "success");
    loadAuditBadge();
    if (relState.mode === "audit") loadRelQueue(1);
  } catch (err) {
    showToast("Gagal terhubung ke server.", "error");
  }
}

// ── Metrik ────────────────────────────────────────────────────────────────

async function loadRelMetrics() {
  try {
    const res = await fetch("/api/admin/relevance/metrics");
    const d = await res.json();
    if (d.status !== "ok") return;
    const pct = (x) => (x === null || x === undefined ? "—" : (x * 100).toFixed(1) + "%");

    const cards = [
      ["Precision", d.sample.precision, d.audit?.precision],
      ["Recall", d.sample.recall, d.audit?.recall],
      ["F1", d.sample.f1, d.audit?.f1],
      ["Akurasi", d.sample.accuracy, d.audit?.accuracy],
    ];
    const cardsHtml = cards
      .map(([label, sampleVal, auditVal]) => `
        <div class="stat-card rel-metric-card">
          <div class="stat-content">
            <span class="stat-label">${label}</span>
            <span class="stat-value">${pct(sampleVal)}</span>
            ${auditVal !== undefined ? `<span class="stat-value-sub">audit: ${pct(auditVal)}</span>` : ""}
          </div>
        </div>`)
      .join("");
    const extraCards = `
      <div class="stat-card rel-metric-card">
        <div class="stat-content"><span class="stat-label">Berlabel</span><span class="stat-value">${d.sample.labeled_count}</span></div>
      </div>
      <div class="stat-card rel-metric-card">
        <div class="stat-content"><span class="stat-label">Gagal Diklasifikasi</span><span class="stat-value" id="relFailedCount">—</span></div>
      </div>`;
    const metricsEl = document.getElementById("relMetrics");
    if (metricsEl) metricsEl.innerHTML = cardsHtml + extraCards;

    const banner = document.getElementById("relBiasBanner");
    if (banner) {
      if (d.bias.warning) {
        banner.textContent = d.bias.warning;
        banner.style.display = "block";
      } else {
        banner.style.display = "none";
      }
    }

    const failedCountEl = document.getElementById("relFailedCount");
    if (failedCountEl) {
      const fr = await fetch("/api/admin/relevance/review-queue?mode=failed&per_page=1");
      const fd = await fr.json();
      if (fd.status === "ok") failedCountEl.textContent = String(fd.total_items);
    }
  } catch (err) {
    console.error(err);
  }
}

// ── Few-shot export ───────────────────────────────────────────────────────

async function openFewShotExport() {
  const btn = document.getElementById("btnExportFewShot");
  if (btn) { btn.disabled = true; btn.textContent = "Memuat..."; }
  try {
    const res = await fetch("/api/admin/relevance/few-shot-export?limit=20");
    const d = await res.json();
    if (d.status !== "ok") { showToast(d.message || "Gagal memuat export.", "warning"); return; }
    const fp = d.corrections.false_positives.length;
    const fn = d.corrections.false_negatives.length;
    document.getElementById("exportMeta").textContent =
      `Total label: ${d.total_labels} — Koreksi: FP=${fp}, FN=${fn} — Konfirmasi dipakai: ${d.confirmations.length}`;
    document.getElementById("exportTextarea").value = d.formatted_prompt;
    document.getElementById("exportModal").classList.remove("hidden");
  } catch (err) {
    showToast("Gagal memuat export.", "error");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "Export Few-Shot"; }
  }
}

// ── Prompt lifecycle: Draft → Dry-Run → Aktifkan ────────────────────────

async function openPromptModal() {
  try {
    const res = await fetch("/api/admin/relevance/prompt");
    const d = await res.json();
    if (d.status !== "ok") { showToast("Gagal memuat info prompt.", "error"); return; }
    renderPromptHistory(d.versions || []);
    document.getElementById("promptCurrentVersion").textContent = d.active.version;
    document.getElementById("promptCurrentText").value = d.active.prompt;
    setPromptStage("draft");
    document.getElementById("promptModal").classList.remove("hidden");
  } catch (err) {
    showToast("Gagal terhubung ke server.", "error");
  }
}

function renderPromptHistory(versions) {
  const wrap = document.getElementById("promptHistoryBody");
  if (!wrap) return;
  wrap.innerHTML = versions
    .map((v) => `
      <tr>
        <td>${escapeHtml(v.version)}</td>
        <td>${v.status === "active" ? '<span class="rel-pill yes">Aktif</span>' : "—"}</td>
        <td>${escapeHtml(v.activated_at || "—")}</td>
        <td>${v.status !== "active" ? `<button class="btn-mini" onclick="rollbackPrompt('${v.version}')">Rollback</button>` : ""}</td>
      </tr>`)
    .join("");
}

function setPromptStage(stage) {
  document.querySelectorAll(".rel-prompt-stage-tabs button").forEach((b) => {
    b.classList.toggle("active", b.dataset.stage === stage);
  });
  document.querySelectorAll("[data-prompt-stage]").forEach((el) => {
    el.style.display = el.dataset.promptStage === stage ? "" : "none";
  });
}

async function generatePromptDraft() {
  const btn = document.getElementById("btnGenerateDraft");
  if (btn) { btn.disabled = true; btn.textContent = "Menyusun draft (AI)..."; }
  try {
    const res = await fetch("/api/admin/relevance/prompt-draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const d = await res.json();
    if (d.status !== "ok") { showToast(d.message || "Gagal generate draft.", "warning", 8000); return; }
    relDraft = { current: d.current_prompt, draft: d.draft_prompt, evalResult: null };
    document.getElementById("promptNextVersion").textContent = d.next_version;
    document.getElementById("promptDraftText").value = d.draft_prompt;
    const notesEl = document.getElementById("promptNotes");
    const modeLabel = d.mode === "reinforce" ? "Reinforce (tidak ada koreksi, mempertajam rubrik)" : "Korektif";
    notesEl.innerHTML = `<strong>Mode: ${modeLabel}</strong> — ${escapeHtml(d.notes || "")}<br>Evidence: ${d.evidence.corrections} koreksi, ${d.evidence.confirmations} konfirmasi (total ${d.evidence.total_labels} label).`;
    notesEl.style.display = "block";
    document.getElementById("btnEvalDraft").disabled = false;
    setPromptStage("draft");
  } catch (err) {
    showToast("Gagal generate draft prompt.", "error");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "Susun Draft (AI)"; }
  }
}

async function evaluatePromptDraft() {
  const draftText = document.getElementById("promptDraftText").value.trim();
  if (draftText.length < 200) { showToast("Draft terlalu pendek untuk diuji.", "warning"); return; }

  const btn = document.getElementById("btnEvalDraft");
  if (btn) { btn.disabled = true; btn.textContent = "Menguji (2x panggilan LLM per baris)..."; }
  try {
    const res = await fetch("/api/admin/relevance/prompt-eval", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ draft_prompt: draftText, sample_size: 40 }),
    });
    const d = await res.json();
    if (d.status !== "ok") { showToast(d.message || "Gagal menguji draft.", "error", 8000); return; }
    relDraft.evalResult = d;
    renderPromptEval(d);
    setPromptStage("eval");
  } catch (err) {
    showToast("Gagal menguji draft.", "error");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "Uji Kering (Dry-Run)"; }
  }
}

function renderPromptEval(d) {
  const pct = (x) => (x === null || x === undefined ? "—" : (x * 100).toFixed(1) + "%");
  const wrap = document.getElementById("promptEvalSummary");
  if (wrap) {
    wrap.innerHTML = `
      <div class="rel-verdict-panel"><h4>Prompt Aktif</h4>
        <p>Precision ${pct(d.active.precision)} · Recall ${pct(d.active.recall)} · F1 ${pct(d.active.f1)}</p></div>
      <div class="rel-verdict-panel"><h4>Draft</h4>
        <p>Precision ${pct(d.draft.precision)} · Recall ${pct(d.draft.recall)} · F1 ${pct(d.draft.f1)}</p></div>`;
  }
  const flipsEl = document.getElementById("promptEvalFlips");
  if (flipsEl) {
    flipsEl.textContent = d.flips.length
      ? `${d.flips.length} keputusan berubah dari ${d.sample_size} sampel (${d.cost_note})`
      : `Tidak ada keputusan yang berubah dari ${d.sample_size} sampel (${d.cost_note})`;
  }
  document.getElementById("btnGoToApply").disabled = false;
}

function skipPromptEval() {
  setPromptStage("apply");
}

async function applyPromptDraft() {
  const confirmation = document.getElementById("promptConfirmInput").value;
  const draftText = document.getElementById("promptDraftText").value.trim();
  const btn = document.getElementById("btnApplyPrompt");
  if (btn) { btn.disabled = true; btn.textContent = "Menyimpan..."; }
  try {
    const res = await fetch("/api/admin/relevance/prompt-apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        draft_prompt: draftText,
        confirmation,
        eval_result: relDraft.evalResult,
      }),
    });
    const d = await res.json();
    if (d.status !== "ok") { showToast(d.message || "Gagal apply prompt.", "error", 8000); return; }
    showToast(d.message || `Prompt ${d.version} aktif.`, "success", 8000);
    document.getElementById("promptModal").classList.add("hidden");
    loadRelMetrics();
  } catch (err) {
    showToast("Gagal apply prompt.", "error");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "Aktifkan Prompt Baru"; }
  }
}

async function rollbackPrompt(version) {
  const confirmed = await showDialog({
    title: `Rollback ke ${version}?`,
    message: "Klasifikasi berikutnya akan memakai versi ini lagi.",
    confirmText: "Ya, Rollback",
    cancelText: "Batal",
    showCancel: true,
    danger: true,
  });
  if (!confirmed) return;

  try {
    const res = await fetch("/api/admin/relevance/prompt-rollback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ version, confirmation: PROMPT_APPLY_CONFIRMATION }),
    });
    const d = await res.json();
    if (d.status !== "ok") { showToast(d.message || "Gagal rollback.", "error"); return; }
    showToast(d.message || `Rollback ke ${version} berhasil.`, "success");
    document.getElementById("promptModal").classList.add("hidden");
    loadRelMetrics();
  } catch (err) {
    showToast("Gagal terhubung ke server.", "error");
  }
}

function bindRelModals() {
  document.getElementById("btnCopyExport")?.addEventListener("click", () => {
    const ta = document.getElementById("exportTextarea");
    navigator.clipboard.writeText(ta.value).then(() => showToast("Tersalin ke clipboard.", "success", 2000));
  });
  document.getElementById("exportModal")?.addEventListener("click", (e) => {
    if (e.target === e.currentTarget) e.currentTarget.classList.add("hidden");
  });
  document.querySelectorAll("[data-close-modal]").forEach((btn) => {
    btn.addEventListener("click", () => document.getElementById(btn.dataset.closeModal)?.classList.add("hidden"));
  });

  document.getElementById("promptModal")?.addEventListener("click", (e) => {
    if (e.target === e.currentTarget) e.currentTarget.classList.add("hidden");
  });
  document.getElementById("btnGenerateDraft")?.addEventListener("click", generatePromptDraft);
  document.getElementById("btnEvalDraft")?.addEventListener("click", evaluatePromptDraft);
  document.getElementById("btnSkipEval")?.addEventListener("click", skipPromptEval);
  document.getElementById("btnGoToApply")?.addEventListener("click", () => setPromptStage("apply"));
  document.getElementById("btnApplyPrompt")?.addEventListener("click", applyPromptDraft);
  document.getElementById("promptConfirmInput")?.addEventListener("input", (e) => {
    document.getElementById("btnApplyPrompt").disabled = e.target.value !== PROMPT_APPLY_CONFIRMATION;
  });
  document.querySelectorAll(".rel-prompt-stage-tabs button").forEach((btn) => {
    btn.addEventListener("click", () => setPromptStage(btn.dataset.stage));
  });
}

// ── Keyboard shortcuts ────────────────────────────────────────────────────

function bindRelKeyboard() {
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.target.closest("input, textarea, select, [contenteditable='true']")) return;

    const key = e.key.toLowerCase();
    if (key === "r" || key === "1") { e.preventDefault(); labelCurrent(true); }
    else if (key === "t" || key === "2") { e.preventDefault(); labelCurrent(false); }
    else if (key === "s" || e.key === " ") { e.preventDefault(); advanceToNext(); }
    else if (key === "u") { e.preventDefault(); undoLastLabel(); }
    else if (key === "c") { e.preventDefault(); reclassifyCurrent(); }
    else if (key === "o") {
      const row = relState.rows[relState.selectedIndex];
      if (row?.url) window.open(row.url, "_blank", "noopener");
    } else if (key === "n") {
      e.preventDefault();
      document.getElementById("relNoteInput")?.focus();
    } else if (key === "x") {
      e.preventDefault();
      const id = relState.selectedId;
      if (id === null) return;
      if (relState.checkedIds.has(id)) relState.checkedIds.delete(id);
      else relState.checkedIds.add(id);
      renderRelQueue();
    } else if (key === "j" || e.key === "ArrowDown") {
      e.preventDefault();
      const next = relState.selectedIndex + 1;
      if (next < relState.rows.length) selectRelItem(relState.rows[next].id, next);
    } else if (key === "k" || e.key === "ArrowUp") {
      e.preventDefault();
      const prev = relState.selectedIndex - 1;
      if (prev >= 0) selectRelItem(relState.rows[prev].id, prev);
    } else if (key === "[") {
      e.preventDefault();
      switchTabBy(-1);
    } else if (key === "]") {
      e.preventDefault();
      switchTabBy(1);
    } else if (key === "/") {
      e.preventDefault();
      document.getElementById("relSearch")?.focus();
    } else if (e.key === "Escape") {
      document.querySelectorAll(".rel-export-modal:not(.hidden)").forEach((m) => m.classList.add("hidden"));
    }
  });
}

function switchTabBy(delta) {
  const idx = REL_TABS.findIndex((t) => t.mode === relState.mode);
  const next = REL_TABS[(idx + delta + REL_TABS.length) % REL_TABS.length];
  document.querySelector(`.rel-tab[data-mode="${next.mode}"]`)?.click();
}
