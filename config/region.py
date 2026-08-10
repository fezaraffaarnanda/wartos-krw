"""
Konstanta wilayah fokus dan identitas aplikasi.

Satu-satunya sumber kebenaran untuk kabupaten yang dipantau. Saat deployment
dipindah ke kabupaten lain, ubah file ini saja — jangan sebar literal nama
daerah ke client BPS, service, atau frontend.
"""

# Kode wilayah Web API BPS
BPS_DOMAIN_ID = 3215  # sebelumnya 3328 (Kabupaten Tegal)
BPS_PDRB_WILAYAH_ID = 3215000

# Label wilayah persis seperti yang dikirim Web API BPS pada field `vervar.label`.
# Dipakai untuk mencocokkan baris wilayah fokus di dalam respons API.
FOCUS_AREA_LABEL = "Kabupaten Karawang"
PROVINCE_LABEL = "Jawa Barat"

# Identitas aplikasi
APP_NAME = "WARTOS"
APP_LONG_NAME = "Warta Online Statistik"
ORG_LABEL = "BPS Kabupaten Karawang"

# ── Sumber berita aktif ─────────────────────────────────────────────────────
# SATU-SATUNYA daftar sumber. Menambah / mengganti / menghapus scraper cukup
# diubah di sini; pipeline (article_pipeline.py), state progress
# (state/scraping.py), endpoint GET /api/sources, dan UI dashboard semuanya
# diturunkan dari konstanta ini — jangan tulis ulang daftar ini di tempat lain.
#
# `key` dipakai sebagai:
#   - key dict progress scraping (state/scraping.py)
#   - suffix id elemen DOM di dashboard (bar-<key>, count-<key>, status-<key>)
# Karena itu key WAJIB huruf kecil/digit/underscore — dijaga
# tests/test_news_sources.py::test_keys_are_dom_id_safe.
NEWS_SOURCES: tuple[tuple[str, str], ...] = (
    ("inews_karawang", "iNews Karawang"),
    ("karawangnews",   "KarawangNews"),
    ("pemda_karawang", "Pemda Karawang"),
    ("radar_karawang", "Radar Karawang"),
)

SOURCE_LABELS: dict[str, str] = dict(NEWS_SOURCES)
SOURCE_KEYS: tuple[str, ...] = tuple(key for key, _ in NEWS_SOURCES)

# Label sumber berita wilayah fokus, persis seperti tersimpan di kolom
# `berita.source`. Dipakai untuk membatasi data yang tampil di dashboard
# (list, ekspor, ringkasan, opsi filter) agar berita warisan wilayah lama
# tidak ikut terbaca.
FOCUS_AREA_SOURCES: tuple[str, ...] = tuple(label for _, label in NEWS_SOURCES)

# ── Pembersihan tag ─────────────────────────────────────────────────────────
# Dipakai utils.tags. Pencocokan memakai bentuk "squashed" (huruf kecil, semua
# non-alfanumerik dibuang), jadi cukup tulis satu bentuk yang wajar:
# "Radar Karawang" otomatis mencakup "radarkarawang", "radar-karawang",
# "Radar  Karawang".

# Identitas media/domain yang bocor jadi tag. Termasuk warisan Tegal supaya
# baris historis ikut bersih saat backfill dijalankan.
NEWS_SOURCE_IDENTITY_TAGS: tuple[str, ...] = (
    # sumber aktif
    "Radar Karawang", "iNews Karawang", "iNews", "KarawangNews",
    "Pemda Karawang", "Pemkab Karawang", "Setda Karawang",
    # warisan Tegal — tetap disaring supaya baris historis ikut bersih
    "Radar Tegal", "Pantura Post", "Tribun Jateng", "TribunJateng",
    "Tribun News", "Tribun", "Kompas", "Setda Tegal",
)

# Nama pejabat/tokoh publik yang muncul sebagai tag orang, bukan topik.
# WAJIB daftar eksplisit — TIDAK ADA heuristik "dua kata berhuruf kapital",
# karena heuristik itu akan ikut membuang nama perusahaan yang sah
# ("Pupuk Indonesia", "Dongsung Chemical", "Aeon Mall").
# Tulis SETIAP varian ejaan yang benar-benar ditemui di data. Gunakan
#   python -m scripts.maintenance.clean_tags_db --report persons
# untuk menemukan kandidat baru, lalu tambahkan manual setelah dicek mata.
# Jangan tambahkan nama depan telanjang (mis. "Aep") — dijaga oleh
# tests/test_tags.py::test_person_blocklist_entries_are_specific.
OFFICIAL_PERSON_TAGS: tuple[str, ...] = (
    "Aep Syaepuloh",
    "Aep Saefullah",
    "Aep Syaepulloh",
    "Cellica Nurrachadiana",
    "Dedi Mulyadi",       # Gubernur Jawa Barat
    "Ahmad Luthfi",       # Gubernur Jawa Tengah
    "Wabup Maslani",      # Wakil Bupati Karawang — "Wabup" di-strip PERSON_TITLE_TOKENS,
                          # jadi tag bare "Maslani" pun otomatis cocok tanpa entri terpisah.
)

# Gelar/jabatan yang di-strip dari awal & akhir tag sebelum dicocokkan ke
# OFFICIAL_PERSON_TAGS. "Bupati Aep Syaepuloh" -> "aep syaepuloh" -> cocok.
# "Bupati" telanjang TIDAK dibuang (itu topik yang sah), dan
# "Kepala Dinas Perdagangan" TIDAK dibuang (itu institusi, bukan orang).
PERSON_TITLE_TOKENS: tuple[str, ...] = (
    "bupati", "wakil bupati", "wabup", "pj bupati", "plt bupati",
    "gubernur", "wakil gubernur", "wagub", "sekda", "sekretaris daerah",
    "kapolres", "kapolsek", "dandim", "danramil",
    "ketua dprd", "wakil ketua dprd", "anggota dprd",
    "camat", "lurah", "kades", "kepala desa",
    "h", "hj", "kh", "drs", "dra", "ir", "dr", "prof",
    "se", "sh", "si", "mm", "msi", "mt", "spd", "mpd",
)
