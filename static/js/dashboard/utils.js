
const _RE_LOCATION_WORD = /(?:tegal|kota tegal|kabupaten tegal|slawi|jawa tengah|jateng|brebes|pemalang|pekalongan|batang|kendal|pemkab|pemkot)/i;

const _STOPWORD_EXACT = new Set([
  "ini", "itu", "dan", "di", "ke", "dari", "yang", "untuk",
  "dengan", "ada", "bisa", "juga", "sudah", "akan", "lagi",
  "oleh", "atau", "saja", "pun", "bila", "jika", "ia", "si",
  "hari", "bulan", "tahun", "orang", "pada", "hal", "cara",
  "bagi", "agar", "saat", "serta", "lebih", "belum", "masih",
  "kami", "kamu", "anda", "kita", "mereka", "dia", "nya",
  "berita", "terbaru", "update",
]);

function _isCleanTag(raw) {
  const t = raw.trim().replace(/^#/, "");
  if (!t) return false;
  if (t.length <= 2) return false;
  if (/^\d+$/.test(t)) return false;
  if (_RE_LOCATION_WORD.test(t)) return false;
  if (_STOPWORD_EXACT.has(t.toLowerCase())) return false;
  return true;
}

function parseDateID(str) {
  if (!str) return new Date(0);
  const m = str.match(/(\d{1,2})\s+(\w+)\s+(\d{4}),?\s+(\d{2}):(\d{2})/);
  if (!m) return new Date(0);
  const [, day, bulan, year, hour, min] = m;
  const month = BULAN_ID[bulan.toLowerCase()];
  if (month === undefined) return new Date(0);
  return new Date(+year, month, +day, +hour, +min);
}

function parseTags(raw) {
  if (!raw) return [];
  return raw
    .split(/\s*\|\s*|,\s*/)
    .map((t) => t.trim().replace(/^#/, ""))
    .filter(Boolean);
}

function parseDateToISO(str) {
  if (!str) return null;
  const d = parseDateID(str);
  if (!d || d.getTime() === 0) return null;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function debounceFilters() {
  if (_filterDebounce) clearTimeout(_filterDebounce);
  _filterDebounce = setTimeout(applyFilters, 350);
}

function applySortDate(arr) {
  arr.sort((a, b) => parseDateID(b.date) - parseDateID(a.date));
}

function _normalizeCitationMarkers(text, prefixes = "S") {
  let normalized = String(text || "");
  const safePrefixes = String(prefixes || "S").replace(/[^A-Z]/gi, "") || "S";
  const cls = `[${safePrefixes}]`;

  // Step 0: Expand bracket berkoma: [P19, P22] → [P19][P22]
  //         atau mixed: [P02, 3, P13] → [P02][P03][P13]
  const commaBracketRe = new RegExp(
    `\\[([${safePrefixes}]\\d{1,2}(?:\\s*,\\s*[${safePrefixes}]?\\d{1,2})+)\\]`,
    "gi"
  );
  normalized = normalized.replace(commaBracketRe, (_, inner) => {
    const tokens = inner.split(",").map((t) => t.trim()).filter(Boolean);
    // Prefix default: ambil dari token pertama yang ada huruf awalan
    let defaultPrefix = safePrefixes[0];
    for (const tok of tokens) {
      const m = tok.match(new RegExp(`^([${safePrefixes}])`, "i"));
      if (m) { defaultPrefix = m[1].toUpperCase(); break; }
    }
    return tokens.map((tok) => {
      const mFull = tok.match(new RegExp(`^([${safePrefixes}])(\\d{1,2})$`, "i"));
      const mNum  = tok.match(/^(\d{1,2})$/);
      if (mFull) return `[${mFull[1].toUpperCase()}${String(parseInt(mFull[2], 10)).padStart(2, "0")}]`;
      if (mNum)  return `[${defaultPrefix}${String(parseInt(mNum[1], 10)).padStart(2, "0")}]`;
      return "";
    }).join("");
  });

  // Step 1: Expand marker tergabung: S01S03S04 → [S01][S03][S04]
  const concatRe = new RegExp(`(?:${cls}\\d{2}){2,}`, "gi");
  normalized = normalized.replace(concatRe, (token) => {
    const parts = token.toUpperCase().match(new RegExp(`${cls}\\d{2}`, "g")) || [];
    return parts.map((p) => `[${p}]`).join("");
  });

  // Step 2: Bungkus marker bare: S01 → [S01] (jika belum dibungkus)
  const singleRe = new RegExp(`(?<!\\[)\\b(${cls}\\d{2})\\b(?!\\])`, "gi");
  normalized = normalized.replace(singleRe, "[$1]");
  return normalized;
}

function _markdownToHtmlSafe(markdownText) {
  const escaped = escapeHtml(markdownText || "");
  if (window.marked && typeof window.marked.parse === "function") {
    return window.marked.parse(escaped, {
      gfm: true,
      breaks: true,
      headerIds: false,
      mangle: false,
    });
  }
  return escaped.replace(/\n/g, "<br>");
}
