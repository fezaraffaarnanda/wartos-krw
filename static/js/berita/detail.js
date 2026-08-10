document.addEventListener("DOMContentLoaded", async () => {
  if (typeof initAppShell === "function") {
    initAppShell();
  }

  if (typeof showPageLoadingOverlay === "function") {
    showPageLoadingOverlay({
      title: "Memuat detail berita...",
      subtitle: "Konten lengkap dan metadata berita sedang disiapkan.",
    });
  }

  const loadingState = document.getElementById("loadingState");
  if (loadingState && typeof getPageLoadingOverlay === "function" && getPageLoadingOverlay()) {
    loadingState.classList.add("is-hidden");
  }

  try {
    await loadUserInfo();
    const id = getArticleId();
    if (!id) {
      showError("ID berita tidak valid.");
      return;
    }

    await loadArticle(id);
  } finally {
    if (typeof hidePageLoadingOverlay === "function") {
      hidePageLoadingOverlay();
    }
  }
});

function getArticleId() {
  const parts = window.location.pathname.split("/");
  const id = parseInt(parts[parts.length - 1], 10);
  return Number.isNaN(id) || id <= 0 ? null : id;
}

async function loadUserInfo() {
  try {
    const res = await fetch("/api/me");
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const json = await res.json();
    if (json.status === "ok") {
      document.getElementById("headerUser").textContent = json.username;
    }
  } catch (_) {
    // abaikan
  }
}

async function loadArticle(id) {
  try {
    const res = await fetch(`/api/berita/${id}`);
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const json = await res.json();

    if (json.status !== "ok" || !json.data) {
      showError(json.message || "Berita tidak ditemukan.");
      return;
    }

    renderArticle(json.data);
    if (typeof trackEvent === "function") trackEvent("berita_detail_open");
  } catch (_) {
    showError("Gagal memuat berita. Coba lagi nanti.");
  }
}

function renderArticle(d) {
  document.title = `${d.title || "Detail Berita"} — WARTOS`;

  document.getElementById("articleTitle").textContent = d.title || "—";
  document.getElementById("articleSource").textContent = d.source || "—";
  document.getElementById("articleDate").textContent = d.date || "—";

  const extLink = document.getElementById("articleExternalLink");
  if (d.url) {
    extLink.href = d.url;
  } else {
    extLink.parentElement.classList.add("is-hidden");
  }

  const tagsContainer = document.getElementById("articleTags");
  if (d.tags) {
    const tags = parseTags(d.tags);
    tagsContainer.innerHTML = tags
      .map((t) => `<span class="tag-chip">#${escapeHtml(t)}</span>`)
      .join(" ");
  }

  renderClassification(d.kbli, d.aktivitas_ekonomi, d.pdrb_pengeluaran);
  renderArchiveStatus(d.is_archived, d.archived_at);

  const bodyEl = document.getElementById("articleBody");
  const paragraphs = (d.content || "Isi berita tidak tersedia.")
    .split(/\n+/)
    .filter((p) => p.trim());
  bodyEl.innerHTML = paragraphs
    .map((p) => `<p>${escapeHtml(p.trim())}</p>`)
    .join("");

  document.getElementById("articleCard").classList.remove("is-hidden");
}

function renderClassification(kbliRaw, aktivitasRaw, pdrbRaw) {
  const section = document.getElementById("articleClassification");
  const kbliBadge = document.getElementById("kbliBadge");
  const aktivitasBadge = document.getElementById("aktivitasBadge");
  const pdrbPengeluaranBadge = document.getElementById("pdrbPengeluaranBadge");

  let hasContent = false;

  if (kbliRaw && kbliRaw.trim()) {
    const raw = kbliRaw.trim();
    const kode = raw.split("/", 1)[0].trim().toUpperCase();
    const label = raw.includes("/") ? raw.split("/", 2)[1].trim() : (KBLI_KEY_MAPPING[kode] || raw);
    const isIrrelevant = kode === "TIDAK RELEVAN" || kode === "—";
    if (isIrrelevant) {
      kbliBadge.textContent = "Tidak Relevan";
      kbliBadge.classList.add("badge-irrelevant");
    } else {
      kbliBadge.innerHTML = label
        ? `<strong>${escapeHtml(kode)}</strong> — ${escapeHtml(label)}`
        : escapeHtml(kode);
    }
    hasContent = true;
  } else {
    kbliBadge.textContent = "Belum diklasifikasi";
    kbliBadge.classList.add("badge-pending");
    hasContent = true;
  }

  if (aktivitasRaw && aktivitasRaw.trim()) {
    const val = aktivitasRaw.trim();
    const isIrrelevant = val.toLowerCase() === "tidak relevan" || val === "—";

    if (isIrrelevant) {
      aktivitasBadge.textContent = "Tidak Relevan";
      aktivitasBadge.classList.add("badge-irrelevant");
    } else {
      const slashIdx = val.indexOf("/");
      if (slashIdx !== -1) {
        const nomor = val.slice(0, slashIdx).trim();
        const label = val.slice(slashIdx + 1).trim();
        aktivitasBadge.innerHTML = `<strong>${escapeHtml(nomor)}</strong> — ${escapeHtml(label)}`;
      } else {
        aktivitasBadge.textContent = val;
      }
    }
    hasContent = true;
  } else {
    aktivitasBadge.textContent = "Belum diklasifikasi";
    aktivitasBadge.classList.add("badge-pending");
    hasContent = true;
  }

  if (pdrbPengeluaranBadge) {
    if (pdrbRaw && pdrbRaw.trim()) {
      const val = pdrbRaw.trim();
      const isNotApplicable = val === "—";
      const isIrrelevant = val.toLowerCase() === "tidak relevan";

      if (isNotApplicable) {
        pdrbPengeluaranBadge.textContent = "Tidak berlaku";
        pdrbPengeluaranBadge.classList.add("badge-pending");
      } else if (isIrrelevant) {
        pdrbPengeluaranBadge.textContent = "Tidak Relevan";
        pdrbPengeluaranBadge.classList.add("badge-irrelevant");
      } else {
        const slashIdx = val.indexOf("/");
        const code = (slashIdx === -1 ? val : val.slice(0, slashIdx)).trim().toUpperCase();
        const label = (slashIdx === -1 ? val : val.slice(slashIdx + 1)).trim();
        const parentCode = getPdrbPengeluaranParentCode(code);
        const parentLabel = PDRB_PENGELUARAN_PARENT_LABELS[parentCode] || "";
        pdrbPengeluaranBadge.innerHTML = `<strong>${escapeHtml(code)}</strong> — ${escapeHtml(label)}${parentLabel ? ` (${escapeHtml(parentLabel)})` : ""}`;
      }
    } else {
      pdrbPengeluaranBadge.textContent = "Belum diklasifikasi";
      pdrbPengeluaranBadge.classList.add("badge-pending");
    }
    hasContent = true;
  }

  if (hasContent) {
    section.classList.remove("is-hidden");
  }
}

function renderArchiveStatus(isArchived, archivedAt) {
  const row = document.getElementById("articleStatusRow");
  const badge = document.getElementById("articleStatusBadge");
  const note = document.getElementById("articleStatusNote");
  if (!row || !badge || !note) return;

  row.classList.remove("is-hidden");
  badge.className = `article-status-chip ${isArchived ? "archived" : "active"}`;
  badge.textContent = isArchived ? "Diarsipkan" : "Aktif";

  if (isArchived && archivedAt) {
    const formatted = formatArchiveDate(archivedAt);
    note.textContent = formatted
      ? `Berita ini sedang disembunyikan dari tabel utama sejak ${formatted}.`
      : "Berita ini sedang disembunyikan dari tabel utama.";
    return;
  }

  note.textContent = "Berita ini tampil di tabel utama dashboard.";
}

function formatArchiveDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("id-ID", {
    day: "2-digit",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function showError(msg) {
  document.getElementById("errorMsg").textContent = msg;
  document.getElementById("errorState").classList.remove("is-hidden");
}
