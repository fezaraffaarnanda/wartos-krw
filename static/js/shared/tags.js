// Pemisah string tag. Penyaringan (lokasi, stopword, identitas sumber, nama
// pejabat) dilakukan SATU kali di server: utils/tags.py, dipanggil saat
// insert (services/article_pipeline.py::_build_article_row) dan oleh backfill
// scripts.maintenance.clean_tags_db. JANGAN membuat mirror aturannya di JS —
// mirror sebelumnya (_isCleanTag di dashboard/utils.js) drift dari aturan
// Python lalu berakhir jadi dead code yang tak pernah dipanggil.

function parseTags(raw) {
  if (!raw) return [];
  return raw
    .split(/\s*\|\s*|,\s*/)
    .map((t) => t.trim().replace(/^#/, ""))
    .filter(Boolean);
}
