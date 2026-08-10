# AGENTS.md

Panduan ini ditujukan untuk agent coding yang bekerja di repo ini.
Fokus utamanya: menjaga konsistensi arsitektur Flask + Supabase + scraper + vanilla JS,
serta menghindari technical debt saat menambah fitur atau refactor.

## Project Summary
- WARTOS (Warta Online Statistik) — aplikasi Flask untuk pemantauan berita ekonomi lokal Kabupaten Karawang.
- Sumber berita aktif: iNews Karawang, KarawangNews, Pemda Karawang, Radar Karawang.
- Wilayah fokus dan identitas aplikasi terpusat di `config/region.py` — jangan sebar literal nama daerah.
- Backend memakai Supabase Postgres via Python client, tanpa ORM.
- Fitur AI: KBLI, aktivitas ekonomi, embedding, AI insights, AI chat.
- Frontend memakai HTML template, CSS, dan vanilla JS modular di `static/js/`.

## Rule Files Discovery
- `.cursorrules`: tidak ada
- `.cursor/rules/`: tidak ada
- `.github/copilot-instructions.md`: tidak ada
- Ikuti file ini dan pola kode existing sebagai source of truth.

## Environment Setup
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Variabel `.env` yang umum dipakai:
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `FLASK_SECRET_KEY`
- `CRON_SECRET`
- `GEMINI_API_KEY`

## Build / Run / Lint / Test Commands
Repo ini belum punya tool build formal, config linter formal, atau suite test bawaan.
File seperti `pyproject.toml`, `pytest.ini`, `tox.ini`, `.flake8`, `.pylintrc`, `package.json` tidak ditemukan.

### Run app
```bash
python app.py
```

### Run scrapers
```bash
python -m scrapers.radartegal
python -m scrapers.panturapost
python -m scrapers.tribunjateng
python -m scrapers.kompas
python -m scrapers.setda_tegal
```

### Run operational scripts
```bash
python -m scripts.users.create_user <username> <password> [role]
python -m scripts.backfill.backfill_kbli
python -m scripts.backfill.backfill_embeddings
python -m scripts.scraping.trigger_scrape --max-articles 150
python -m scripts.reference_data.build_kbli_embeddings
python -m scripts.maintenance.clean_tags_db
```

### Smoke checks
```bash
python -m compileall .
node --check static/js/dashboard/bootstrap.js
node --check static/js/auth/login.js
```

### Test commands
Belum ada test aktif. Jika agent menambah test, default gunakan `pytest`.
```bash
python -m pytest
python -m pytest tests/test_something.py
python -m pytest tests/test_something.py::test_case_name
python -m pytest tests/test_something.py -k partial_name
```

Alternatif `unittest`:
```bash
python -m unittest discover -s tests -p "test_*.py"
python -m unittest tests.test_module.TestClass.test_method
```

## Repository Layout
- `app.py`: bootstrap Flask app dan init startup.
- `routes/`: endpoint HTTP per domain.
- `services/`: orchestration aplikasi dan pipeline artikel.
- `ai/`: logic AI, embedding, KBLI, aktivitas, insight, chat.
- `repositories/`: akses data Supabase per domain.
- `clients/`: client eksternal seperti Supabase dan LLM.
- `config/`: Flask extensions dan bootstrap config.
- `utils/`: helper Python kecil dan murni.
- `state/`: shared runtime state.
- `scrapers/`: scraper per sumber berita.
- `scripts/`: utility CLI dan backfill.
- `static/js/`: JS frontend modular per domain.
- `templates/`: halaman HTML Flask.

## Core Contracts

### Scraper contract
Setiap scraper wajib mempertahankan kontrak berikut:
```python
def scrape_new_articles(existing_urls: set, max_articles: int, on_progress=None) -> list[dict]:
    ...
```
Minimal field hasil artikel: `title`, `date`, `url`, `content`, `tags`, `source`.

### API response contract
- sukses: `{"status": "ok", ...}`
- gagal: `{"status": "error", "message": "..."}`

### Date contract
- Format tampilan target: `DD MMMM YYYY, HH:MM WIB`
- Normalisasi tanggal Python ada di `utils/date.py`
- Frontend parsing tanggal harus tetap kompatibel dengan format itu.

## Python Style Guide

### Imports
- Urutan import: standard library -> third-party -> local
- Pisahkan tiap grup import dengan satu baris kosong
- Gunakan multi-line import bertanda kurung untuk import panjang

### Formatting
- Indent 4 spasi, tanpa tab
- Target line length sekitar 100 karakter
- Gunakan trailing comma pada struktur multiline
- Pertahankan comment section yang memang membantu navigasi file

### Types
- Gunakan type hints pada fungsi penting, terutama service, repository, scraper, helper shared
- Pakai syntax modern Python 3.10+: `X | Y`, `list[str]`, `dict[str, Any]`

### Naming
- fungsi/variabel: `snake_case`
- class: `PascalCase`
- konstanta: `UPPER_SNAKE_CASE`
- helper internal/private: prefix `_`
- nama file/folder harus berbasis domain/tujuan, hindari `misc`, `helpers`, `new`, `v2`

### Error handling
- Tangani boundary I/O dengan `try/except Exception`
- Gunakan log sederhana dengan prefix jelas, mis. `[SCRAPE]`, `[AUTH]`, `[AI]`
- Error ke user harus ringkas dan aman; jangan bocorkan detail sensitif
- Operasi non-kritis boleh fail-soft, operasi kritis harus return error eksplisit

## Frontend JavaScript Style
- Pertahankan modularisasi per domain di `static/js/`
- Shared helper hanya untuk logic yang benar-benar dipakai lintas halaman
- fungsi/variabel: `camelCase`
- konstanta module-level: `UPPER_SNAKE_CASE`
- helper internal boleh prefix `_`
- Jangan ubah nama fungsi global yang masih dipakai inline HTML tanpa update template
- Jangan ubah urutan load script di template secara sembarangan
- Jika memecah file JS, pastikan state shared tidak terduplikasi

## Database / Data Guidance
- Gunakan Supabase Python client fluent API, bukan ORM tambahan
- Jangan ubah schema database dari runtime code
- Perubahan schema harus lewat migration SQL terpisah
- Jika menambah field artikel, sinkronkan pipeline insert, export, AI, dan frontend

## Scraper Guidance
- Gunakan `requests` + `BeautifulSoup` sesuai pola existing
- Gunakan header browser-like dan retry/delay yang masuk akal
- Filter boilerplate konten dengan regex dan cleaning per baris
- Jaga mode standalone scraper tetap bisa dijalankan dengan `python -m ...`

## Working Rules for Agents
- Bahasa untuk teks user-facing, log, komentar, dan docstring: Bahasa Indonesia
- Jangan commit `.env`, token, kredensial, atau data sensitif
- Jangan ubah behavior UI/API/output tanpa permintaan eksplisit user
- Untuk refactor besar, prioritaskan perubahan bertahap dan backward-compatible
- Sebelum menghapus file lama, pastikan semua template/import sudah pindah ke path baru
- Saat mengubah route/API, cek dampaknya ke `static/js/dashboard/`, script halaman terkait, dan template
- Setelah perubahan Python atau JS, lakukan minimal satu smoke check yang relevan
