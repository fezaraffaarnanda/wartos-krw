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
