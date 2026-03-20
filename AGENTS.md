# AGENTS.md

Panduan ini ditujukan untuk coding agent yang bekerja di repository ini.
Tujuan utamanya: menjaga konsistensi arsitektur Flask, alur scraping, dan gaya kode yang sudah ada.

## Project Overview

- Aplikasi Flask untuk scraping berita wilayah Tegal dari beberapa sumber:
  Radar Tegal, Pantura Post, Tribun Jateng, Kompas, Setda Tegal.
- Data disimpan ke Supabase Postgres (tanpa ORM), terutama pada tabel `berita`, `scrape_log`, dan `users`.
- Fitur AI meliputi insight indikator, klasifikasi KBLI, aktivitas ekonomi, embedding, dan AI chat.
- Teks user-facing, pesan API, log, komentar, dan docstring menggunakan Bahasa Indonesia.

## Rule Files Discovery

Hasil pengecekan file aturan tambahan:

- `.cursorrules`: tidak ditemukan.
- `.cursor/rules/`: tidak ditemukan.
- `.github/copilot-instructions.md`: tidak ditemukan.

Karena tidak ada rule file lain, ikuti AGENTS.md ini dan pola dari kode existing.

## Environment Setup

```bash
python -m venv venv
source venv/bin/activate              # macOS/Linux
# venv\Scripts\activate              # Windows
pip install -r requirements.txt
```

Variabel `.env` minimum:

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `FLASK_SECRET_KEY`
- `CRON_SECRET`
- `GEMINI_API_KEY` (wajib untuk fitur AI, opsional untuk boot dasar)

## Build / Run / Lint / Test Commands

Repository ini saat ini **tidak memiliki** tool build formal, linter wajib, atau test suite bawaan.
File seperti `pyproject.toml`, `pytest.ini`, `tox.ini`, `.flake8`, `.pylintrc` tidak ditemukan.

Perintah operasional utama:

```bash
# Jalankan aplikasi Flask (dev)
python app.py

# Jalankan scraper per sumber (standalone)
python -m scrapers.scrape_radartegal_bs4
python -m scrapers.scraping_panturapost
python -m scrapers.scrape_tribunjateng_v2
python -m scrapers.scrape_kompas
python -m scrapers.scraping_tegal

# Utility data/user
python tools/create_user.py <username> <password> [role]
python tools/backfill_kbli.py
python tools/backfill_embeddings.py
```

### Test Commands (terutama single test)

- Belum ada file test bawaan (`test_*.py` / `*_test.py` tidak ditemukan).
- Jika menambahkan test, gunakan konvensi ini:

```bash
# Semua test (pytest)
python -m pytest

# Satu file test
python -m pytest tests/test_something.py

# Single test case (penting)
python -m pytest tests/test_something.py::test_case_name
```

Jika menggunakan `unittest`:

```bash
# Semua unittest
python -m unittest discover -s tests -p "test_*.py"

# Single unittest
python -m unittest tests.test_something.TestClass.test_method
```

## Arsitektur Singkat

- `app.py`: app factory, registrasi blueprint, init classifier/client, startup background thread.
- `routes/`: endpoint per domain (`auth`, `berita`, `scraping`, `admin`, `ai_insights`, `ai_chat`, `pages`).
- `core/`: logika pipeline artikel, state, util tanggal/tag, helper DB, client LLM/embedding.
- `scrapers/`: scraper per media dengan kontrak output yang konsisten.
- `tools/`: script utilitas maintenance dan backfill.

## Kontrak Penting

### Scraper Contract

Semua module scraper wajib menyediakan:

```python
def scrape_new_articles(existing_urls: set, max_articles: int, on_progress=None) -> list[dict]:
    ...
```

Minimal field artikel: `title`, `date`, `url`, `content`, `tags`, `source`.

### Date Handling

- Semua tanggal dinormalisasi via `core/utils.py` (`normalize_date`).
- Format target: `DD MMMM YYYY, HH:MM WIB`.
- Simpan versi ISO menggunakan `parse_date_to_iso()` ke kolom `date_parsed`.

### Duplicate & Concurrency

- Duplicate dicegah berbasis URL (`_fetch_existing_urls` + UNIQUE `berita.url`).
- Shared state scraping berada di `core/state.py`.
- Gunakan `_scraping_lock` untuk mencegah scrape paralel yang bentrok.
- Endpoint `/api/scrape` mendukung dual auth: session admin dan bearer `CRON_SECRET`.

## Code Style Guidelines

### Language & Messaging

- Semua teks user-facing, log, komentar, dan docstring harus Bahasa Indonesia.
- Error autentikasi harus generik (jangan bocorkan detail kredensial yang salah).

### Imports

- Urutan import: standard library -> third-party -> local.
- Pisahkan grup import dengan satu baris kosong.
- Untuk import panjang di Flask route/module, gunakan multi-line import bertanda kurung.

### Formatting

- Indent 4 spasi, tanpa tab.
- Soft line length sekitar 100 karakter.
- Pertahankan gaya section header existing:
  `# ── Nama Section ─────────────────────────`
- Gunakan trailing comma pada struktur multiline.
- Alignment spasi antar assignment boleh dipakai jika konsisten dalam blok yang sama.

### Naming Conventions

- Fungsi/variabel: `snake_case`.
- Class: `PascalCase`.
- Konstanta module-level: `UPPER_SNAKE_CASE`.
- Helper private/internal: prefix underscore (`_helper_name`).
- Regex compiled di module-level mengikuti pola `_UPPER_SNAKE_CASE`.

### Typing

- Gunakan type hints pada signature fungsi penting (publik/internal).
- Gunakan syntax union modern `X | Y` (Python 3.10+), bukan `Optional[X]`.
- Gunakan generic builtin (`list[dict]`, `set[str]`) dibanding typing legacy.

### Error Handling

- Tangani boundary I/O (HTTP scraper, DB, client AI) dengan `try/except Exception`.
- Log sederhana dengan `print` dan prefix tag (contoh: `[SCRAPE]`, `[DB ERROR]`, `[AUTH]`).
- Response API Flask konsisten:
  - sukses: `{"status": "ok", ...}`
  - gagal: `{"status": "error", "message": "..."}` + HTTP status relevan
- Operasi non-kritis boleh fail-soft; operasi kritis wajib return error eksplisit.

### Data & DB

- Gunakan Supabase Python client fluent API untuk query DB.
- Jangan ubah schema dari runtime code; lakukan melalui migration SQL terpisah.
- Jika menambah field artikel, pastikan kompatibel dengan insert pipeline + backfill.

### Scraper Conventions

- Gunakan `requests` + `BeautifulSoup` dengan header browser-like.
- Terapkan retry/backoff + delay acak antar request.
- Bersihkan boilerplate konten dengan regex + filter per baris.
- Pertahankan mode standalone tiap scraper (`if __name__ == "__main__":`).

## Operational Notes

- Jangan commit `.env` atau kredensial.
- Hindari refactor lintas modul besar tanpa permintaan eksplisit user.
- Saat mengubah route/API, cek dampaknya ke `static/js/script.js` dan template.
- Saat menambah fitur AI, sediakan fallback aman jika `GEMINI_API_KEY` tidak tersedia.
- Jaga kompatibilitas deployment Vercel (hindari pekerjaan berat sinkron di request path biasa).
