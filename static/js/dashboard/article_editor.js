document.addEventListener("DOMContentLoaded", () => {
  initArticleEditor();
  syncArchiveFilterButtons();
});

function initArticleEditor() {
  const backdrop = document.getElementById("articleEditorBackdrop");
  const form = document.getElementById("articleEditorForm");

  if (backdrop && !backdrop.dataset.init) {
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) {
        closeArticleEditor();
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !backdrop.hidden) {
        closeArticleEditor();
      }
    });

    backdrop.dataset.init = "1";
  }

  if (form && !form.dataset.init) {
    form.addEventListener("submit", submitArticleClassification);
    form.dataset.init = "1";
  }

  populateArticleEditorOptions();
}

function populateArticleEditorOptions() {
  const kbliSelect = document.getElementById("articleEditorKbli");
  const aktivitasSelect = document.getElementById("articleEditorAktivitas");
  const pdrbSelect = document.getElementById("articleEditorPdrbPengeluaran");
  if (!kbliSelect || !aktivitasSelect || !pdrbSelect) return;

  const kbliOptions = [
    '<option value="">Pilih kategori KBLI</option>',
    '<option value="TIDAK RELEVAN">Tidak Relevan</option>',
    ...Object.keys(KBLI_KEY_MAPPING).map(
      (code) => `<option value="${escapeAttr(code)}">${escapeHtml(code)} — ${escapeHtml(KBLI_KEY_MAPPING[code])}</option>`,
    ),
  ];

  const aktivitasOptions = [
    '<option value="">Pilih aktivitas ekonomi</option>',
    '<option value="—">Tidak Berlaku</option>',
    '<option value="Tidak Relevan">Tidak Relevan</option>',
    ...Object.keys(AKTIVITAS_LABELS)
      .sort((a, b) => Number(a) - Number(b))
      .map(
        (code) => `<option value="${escapeAttr(code)}">${escapeHtml(code)} — ${escapeHtml(AKTIVITAS_LABELS[Number(code)])}</option>`,
      ),
  ];

  const pdrbOptions = [
    '<option value="">Pilih kategori PDRB pengeluaran</option>',
    '<option value="—">Tidak Berlaku</option>',
    '<option value="Tidak Relevan">Tidak Relevan</option>',
    ...Object.keys(PDRB_PENGELUARAN_LABELS)
      .sort(
        (a, b) =>
          (PDRB_PENGELUARAN_CODE_ORDER[a] || 0) -
          (PDRB_PENGELUARAN_CODE_ORDER[b] || 0),
      )
      .map((code) => {
        const parentCode = getPdrbPengeluaranParentCode(code);
        const parentLabel = PDRB_PENGELUARAN_PARENT_LABELS[parentCode] || parentCode;
        return `<option value="${escapeAttr(code)}">${escapeHtml(code)} — ${escapeHtml(PDRB_PENGELUARAN_LABELS[code])}${parentLabel ? ` (${escapeHtml(parentLabel)})` : ""}</option>`;
      }),
  ];

  kbliSelect.innerHTML = kbliOptions.join("");
  aktivitasSelect.innerHTML = aktivitasOptions.join("");
  pdrbSelect.innerHTML = pdrbOptions.join("");
}

function openArticleEditor(article) {
  initArticleEditor();

  _articleEditorState = {
    beritaId: Number(article?.id || 0),
    title: String(article?.title || "").trim(),
    source: String(article?.source || "").trim(),
    kbliCode: String(article?.kbliCode || "").trim(),
    aktivitasCode: String(article?.aktivitasCode || "").trim(),
    pdrbPengeluaranCode: String(article?.pdrbPengeluaranCode || "").trim(),
    isArchived: Boolean(article?.isArchived),
  };

  const backdrop = document.getElementById("articleEditorBackdrop");
  const titleEl = document.getElementById("articleEditorArticleTitle");
  const metaEl = document.getElementById("articleEditorArticleMeta");
  const subtitleEl = document.getElementById("articleEditorSubtitle");
  const kbliSelect = document.getElementById("articleEditorKbli");
  const aktivitasSelect = document.getElementById("articleEditorAktivitas");
  const pdrbSelect = document.getElementById("articleEditorPdrbPengeluaran");

  if (!backdrop || !kbliSelect || !aktivitasSelect || !pdrbSelect) return;

  resetArticleEditorMessage();

  if (titleEl) titleEl.textContent = _articleEditorState.title || "Berita tanpa judul";
  if (metaEl) {
    metaEl.textContent = _articleEditorState.source
      ? `Sumber: ${_articleEditorState.source}`
      : "Sumber berita tidak tersedia";
  }
  if (subtitleEl) {
    subtitleEl.textContent = _articleEditorState.isArchived
      ? "Berita ini sedang diarsipkan. Anda tetap bisa memperbarui klasifikasinya."
      : "Perbarui KBLI, aktivitas ekonomi, dan kategori PDRB pengeluaran yang paling sesuai.";
  }

  kbliSelect.value = _articleEditorState.kbliCode || "";
  aktivitasSelect.value = _articleEditorState.aktivitasCode || "";
  pdrbSelect.value = _articleEditorState.pdrbPengeluaranCode || "";

  backdrop.hidden = false;
  document.body.style.overflow = "hidden";
  window.setTimeout(() => kbliSelect.focus(), 30);
}

function openArticleEditorById(beritaId) {
  const article = (filteredData || []).find((item) => Number(item.id) === Number(beritaId));
  if (!article) return;

  openArticleEditor({
    id: article.id,
    title: article.title,
    source: article.source,
    kbliCode: getKbliCode(article.kbli || ""),
    aktivitasCode: getAktivitasCode(article.aktivitas_ekonomi || ""),
    pdrbPengeluaranCode: getPdrbPengeluaranCode(article.pdrb_pengeluaran || ""),
    isArchived: article.is_archived,
  });
}

function closeArticleEditor() {
  const backdrop = document.getElementById("articleEditorBackdrop");
  if (!backdrop) return;
  backdrop.hidden = true;
  document.body.style.overflow = "";
  resetArticleEditorMessage();
}

function resetArticleEditorMessage() {
  const messageEl = document.getElementById("articleEditorMessage");
  if (!messageEl) return;
  messageEl.className = "article-editor-message";
  messageEl.textContent = "";
}

function setArticleEditorMessage(message, tone = "info") {
  const messageEl = document.getElementById("articleEditorMessage");
  if (!messageEl) return;
  messageEl.className = `article-editor-message ${tone}`;
  messageEl.textContent = message;
}

async function submitArticleClassification(event) {
  event.preventDefault();

  const beritaId = Number(_articleEditorState?.beritaId || 0);
  const kbliCode = document.getElementById("articleEditorKbli")?.value || "";
  const aktivitasCode = document.getElementById("articleEditorAktivitas")?.value || "";
  const pdrbPengeluaranCode =
    document.getElementById("articleEditorPdrbPengeluaran")?.value || "";
  const submitBtn = document.getElementById("articleEditorSubmitBtn");

  if (!beritaId) {
    setArticleEditorMessage("Data berita tidak valid.", "error");
    return;
  }

  if (!kbliCode || !aktivitasCode || !pdrbPengeluaranCode) {
    setArticleEditorMessage(
      "KBLI, aktivitas ekonomi, dan PDRB pengeluaran wajib dipilih.",
      "error",
    );
    return;
  }

  setArticleEditorMessage("Menyimpan perubahan...", "info");
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = "Menyimpan...";
  }

  try {
    const response = await fetch(`/api/berita/${beritaId}/classification`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kbli_code: kbliCode,
          aktivitas_code: aktivitasCode,
          pdrb_pengeluaran_code: pdrbPengeluaranCode,
        }),
    });

    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }

    const json = await response.json();
    if (!response.ok || json.status !== "ok") {
      setArticleEditorMessage(json.message || "Gagal menyimpan klasifikasi.", "error");
      return;
    }

    setArticleEditorMessage(json.message || "Klasifikasi berhasil diperbarui.", "success");
    await loadBerita();
    window.setTimeout(() => closeArticleEditor(), 500);
  } catch (error) {
    console.error("Gagal menyimpan klasifikasi:", error);
    setArticleEditorMessage("Gagal terhubung ke server.", "error");
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = "Simpan Perubahan";
    }
  }
}

function syncArchiveFilterButtons() {
  const buttons = {
    relevant: document.getElementById("archiveFilterRelevant"),
    active: document.getElementById("archiveFilterActive"),
    archived: document.getElementById("archiveFilterArchived"),
    all: document.getElementById("archiveFilterAll"),
  };

  Object.entries(buttons).forEach(([key, button]) => {
    if (!button) return;
    button.classList.toggle("active", key === _selectedArchiveStatus);
  });
}

function selectArchiveFilter(status) {
  _selectedArchiveStatus = status || "relevant";
  _tableFilterState.archive_status = _selectedArchiveStatus;
  syncArchiveFilterButtons();
  currentPage = 1;
  loadBerita();
}

async function toggleArticleArchive(beritaId, shouldArchive) {
  const article = (filteredData || []).find((item) => Number(item.id) === Number(beritaId));
  const articleTitle = article?.title || "tanpa judul";
  const actionLabel = shouldArchive ? "arsipkan" : "pulihkan";
  const confirmed = await showChatDialog({
    title: shouldArchive ? "Arsipkan berita?" : "Pulihkan berita?",
    message: `Berita \"${articleTitle || "tanpa judul"}\" akan ${actionLabel}.`,
    confirmText: shouldArchive ? "Ya, Arsipkan" : "Ya, Pulihkan",
    cancelText: "Batal",
    showCancel: true,
    danger: shouldArchive,
  });

  if (!confirmed) return;

  try {
    const response = await fetch(`/api/berita/${beritaId}/archive`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_archived: shouldArchive }),
    });

    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }

    const json = await response.json();
    if (!response.ok || json.status !== "ok") {
      await showChatDialog({
        title: "Aksi gagal",
        message: json.message || `Gagal ${actionLabel} berita.`,
        confirmText: "Tutup",
        showCancel: false,
      });
      return;
    }

    await loadBerita();
  } catch (error) {
    console.error("Gagal memperbarui arsip berita:", error);
    await showChatDialog({
      title: "Koneksi gagal",
      message: "Gagal terhubung ke server.",
      confirmText: "Tutup",
      showCancel: false,
    });
  }
}
