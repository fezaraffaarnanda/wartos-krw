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

# Label sumber berita wilayah fokus, persis seperti tersimpan di kolom
# `berita.source`. Dipakai untuk membatasi data yang tampil di dashboard
# (list, ekspor, ringkasan, opsi filter) agar berita warisan wilayah lama
# tidak ikut terbaca. Harus selalu sama dengan nilai
# `services.article_pipeline.SOURCE_LABELS` — dijaga oleh
# tests/test_berita_service.py::test_focus_area_sources_match_pipeline.
FOCUS_AREA_SOURCES = (
    "iNews Karawang",
    "KarawangNews",
    "Pemda Karawang",
    "Radar Karawang",
)
