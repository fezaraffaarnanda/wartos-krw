# KABARE

KABARE adalah aplikasi pemantauan berita ekonomi lokal untuk Kabupaten Tegal yang menggabungkan scraping multi-sumber, klasifikasi otomatis, statistik resmi BPS, dan fitur AI berbasis Gemini. Proyek ini ditujukan untuk membantu tim BPS atau analis daerah membaca dinamika ekonomi lapangan dengan lebih cepat, lebih rapi, dan lebih kontekstual.

## URL : kabare.bpstegalkab.web.id

## Daftar Isi

- [Gambaran Singkat](#gambaran-singkat)
- [Fitur Utama](#fitur-utama)
- [Tech Stack](#tech-stack)
- [Struktur Proyek](#struktur-proyek)
- [Arsitektur Singkat](#arsitektur-singkat)
- [Cara Kerja Sistem](#cara-kerja-sistem)
- [Prasyarat](#prasyarat)
- [Instalasi dan Menjalankan Lokal](#instalasi-dan-menjalankan-lokal)
- [Konfigurasi Environment](#konfigurasi-environment)
- [Penggunaan Gemini API](#penggunaan-gemini-api)
- [Penggunaan Web API BPS](#penggunaan-web-api-bps)
- [Ringkasan Endpoint](#ringkasan-endpoint)
- [Perintah Penting](#perintah-penting)
- [Data dan Database](#data-dan-database)
- [Scraper yang Digunakan](#scraper-yang-digunakan)
- [Testing dan Validasi](#testing-dan-validasi)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Developer](#developer)

## Gambaran Singkat

Fungsi utama KABARE adalah mengumpulkan berita ekonomi dari portal lokal dan nasional yang relevan dengan Tegal, menyimpannya ke Supabase, lalu memperkaya berita tersebut dengan:

- klasifikasi KBLI,
- label aktivitas ekonomi,
- kategori PDRB pengeluaran,
- insight AI untuk PDRB, kemiskinan, dan pengangguran,
- chatbot analitik berbasis RAG,
- serta statistik resmi BPS sebagai pembanding.

Dengan pendekatan ini, dashboard tidak hanya menampilkan berita, tetapi juga membantu menjawab pertanyaan seperti: apa sektor yang sedang bergerak, apa isu yang bisa memengaruhi indikator resmi, dan berita mana yang paling relevan untuk analisis statistik daerah.

## Fitur Utama

- Scraping otomatis dari 5 sumber berita yang relevan untuk Kabupaten Tegal dan sekitarnya.
- Dashboard berita dengan filter, pencarian, pagination, ekspor, dan detail artikel.
- Role `admin` dan `user` dengan manajemen akun, reset password, dan kontrol akses.
- Klasifikasi otomatis ke KBLI 2025, aktivitas ekonomi, dan PDRB pengeluaran.
- AI Insights untuk tiga tema utama: PDRB, kemiskinan, dan pengangguran.
- AI Chat berbasis RAG yang menjawab dari konteks berita dan statistik resmi.
- Integrasi statistik resmi BPS untuk memperkaya konteks analisis.
- Progress scraping, log scraping terakhir, dan backfill klasifikasi/embedding.
- Arsip berita dan koreksi klasifikasi manual dari sisi aplikasi.

## Tech Stack

- **Language**: Python
- **Backend Framework**: Flask
- **Authentication**: `flask-login`, `flask-bcrypt`
- **Rate Limiting**: `flask-limiter`
- **Configuration**: `python-dotenv`, `pydantic-settings`
- **Database / Backend Service**: Supabase Postgres
- **Data Access**: Supabase Python client tanpa ORM tambahan
- **Scraping**: `requests` + `beautifulsoup4`
- **Data Processing**: `pandas`, `openpyxl`
- **AI Client**: OpenAI-compatible client, diarahkan ke Google Gemini endpoint
- **Embedding**: Gemini `gemini-embedding-001`
- **Chat / Insight Model**: Gemini `gemini-3.1-flash-lite-preview`
- **Frontend**: HTML template + CSS + vanilla JavaScript modular
- **Testing**: `pytest`
- **Deployment Signal yang Terdeteksi**: repo pernah dikaitkan ke Vercel melalui `.vercel/project.json`, tetapi konfigurasi deployment lengkap tidak disimpan di repo

## Struktur Proyek

Struktur folder inti repo ini:

```text
.
├── app.py                      # entry point Flask dan bootstrap aplikasi
├── config/                     # settings dan Flask extensions
├── routes/                     # endpoint HTML dan API per domain
├── services/                   # orchestration logic / business flow
├── repositories/               # akses data ke Supabase
├── clients/                    # client eksternal: Supabase, LLM, BPS
├── ai/                         # embedding, chat, insight, classifier
├── scrapers/                   # scraper per portal berita
├── schemas/                    # validasi payload / query
├── static/js/                  # JavaScript frontend modular
├── templates/                  # halaman HTML
├── scripts/                    # utilitas operasional dan backfill
├── state/                      # shared runtime state untuk insight/scraping
├── migrations/                 # SQL migration manual
├── data/reference/             # file referensi KBLI, aktivitas, PDRB
└── tests/                      # test pytest yang sudah tersedia
```

## Arsitektur Singkat

Arsitektur aplikasi ini sengaja sederhana dan cukup mudah diikuti:

- **Flask** menangani halaman web, session login, dan endpoint API.
- **Supabase** dipakai sebagai penyimpanan utama data berita, user, log, chat, insight, dan snapshot statistik.
- **Scraper** mengambil berita dari beberapa portal lalu mengirim hasilnya ke pipeline pemrosesan.
- **Pipeline artikel** membersihkan data, memberi label klasifikasi, membuat embedding, lalu menyimpan ke database.
- **Frontend vanilla JS** mengambil data dari API Flask dan menampilkan dashboard.
- **Gemini API** dipakai untuk embedding, AI insight, dan AI chat.
- **Web API BPS** dipakai untuk statistik resmi yang ditampilkan di dashboard dan dipakai sebagai konteks analitik AI.

Secara praktis, alurnya adalah: berita masuk -> diperkaya AI -> disimpan -> ditampilkan di dashboard -> bisa dianalisis lagi lewat insight dan chat.

## Cara Kerja Sistem

### 1. Alur berita

1. Scraper mengambil artikel baru dari portal sumber.
2. Sistem mengecek URL yang sudah pernah disimpan agar tidak duplikat.
3. Artikel divalidasi lalu dinormalisasi tanggal, tag, sumber, dan isi.
4. Artikel diklasifikasikan ke KBLI, aktivitas ekonomi, dan PDRB pengeluaran.
5. Sistem membuat embedding untuk semantic search.
6. Data disimpan ke tabel `berita` di Supabase.
7. Dashboard menampilkan berita terbaru beserta filter dan statistik ringkas.

### 2. Alur insight AI

1. User memilih periode insight.
2. Sistem mengambil berita pada periode tersebut.
3. Sistem mencari artikel paling relevan per kategori.
4. Jika tersedia, statistik resmi BPS ikut dimasukkan sebagai baseline.
5. Gemini menghasilkan insight naratif untuk PDRB, kemiskinan, dan pengangguran.
6. Hasil disimpan agar bisa dipakai ulang tanpa regenerasi terus-menerus.

### 3. Alur AI chat

1. User mengirim pertanyaan melalui chat.
2. Sistem melakukan semantic search ke berita yang relevan.
3. Sistem menambahkan riwayat percakapan dan statistik resmi bila topiknya cocok.
4. Gemini menyusun jawaban berdasarkan konteks tersebut.
5. Jawaban dikembalikan lengkap dengan sitasi berita.

## Prasyarat

Sebelum menjalankan aplikasi, siapkan:

- Python 3.13
- `pip`
- virtual environment (`venv` direkomendasikan)
- akun dan project Supabase
- API key Gemini
- API key Web API BPS jika ingin fitur statistik resmi aktif

Opsional tapi sangat membantu:

- Node.js untuk smoke check file JavaScript
- akses ke dashboard Supabase SQL editor untuk menjalankan migration

## Instalasi dan Menjalankan Lokal

### 1. Clone repository

```bash
git clone <url-repository>
cd crawl-berita-bps-tegal
```

### 2. Buat virtual environment

```bash
python -m venv venv
source venv/bin/activate
```

Untuk Windows PowerShell:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

### 3. Install dependency Python

```bash
pip install -r requirements.txt
```

### 4. Siapkan file environment

Buat file `.env` manual di root project.

Untuk FLASK_SECRET_KEY dan CRON_SECRET hubungi Feza

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-service-key-or-api-key
FLASK_SECRET_KEY=your-random-secret
CRON_SECRET=your-cron-secret
GEMINI_API_KEY=your-gemini-api-key
BPS_API_KEY=your-bps-api-key
```

### 6. Jalankan aplikasi

```bash
python app.py
```

Server default berjalan di:

```text
http://localhost:5000
```

### 7. Login ke aplikasi

Gunakan akun yang sudah ada di database, atau buat akun baru lewat script admin jika skema user sudah siap.

Contoh:

```bash
python -m scripts.users.create_user <username> <password> [role]
```

## Konfigurasi Environment

Semua environment variable dibaca dari `config/settings.py`.

### Variabel utama

| Variable             | Wajib                 | Fungsi                                             |
| -------------------- | --------------------- | -------------------------------------------------- |
| `SUPABASE_URL`     | Ya                    | URL project Supabase                               |
| `SUPABASE_KEY`     | Ya                    | Key untuk akses database dan RPC Supabase          |
| `FLASK_SECRET_KEY` | Ya                    | Secret session Flask                               |
| `CRON_SECRET`      | Disarankan            | Token otorisasi untuk trigger scraping non-session |
| `GEMINI_API_KEY`   | Ya untuk AI           | Mengaktifkan embedding, AI chat, dan AI insight    |
| `BPS_API_KEY`      | Opsional tapi penting | Mengaktifkan statistik resmi BPS                   |

### Catatan penting

- Jika `GEMINI_API_KEY` tidak tersedia, fitur chat, insight, dan klasifikasi berbasis LLM tidak akan berfungsi penuh.
- Jika `BPS_API_KEY` tidak tersedia, statistik resmi BPS tidak bisa dimuat.
- Jangan commit `.env` ke repository.

## Penggunaan Gemini API

Integrasi Gemini adalah komponen penting di repo ini.

### Dipakai untuk apa saja?

#### 1. Embedding artikel

- File utama: `ai/embeddings.py`
- Model: `gemini-embedding-001`
- Fungsi: membuat vector embedding berita agar semantic search di Supabase/pgvector bisa bekerja

#### 2. AI Chat

- File utama: `ai/chat.py`
- Client builder: `clients/llm.py`
- Model: `gemini-3.1-flash-lite-preview`
- Fungsi: menjawab pertanyaan user berdasarkan konteks berita dan statistik resmi

#### 3. AI Insights

- File utama: `ai/insights.py`
- Model: `gemini-3.1-flash-lite-preview`
- Fungsi: menyusun insight ringkas per periode untuk PDRB, kemiskinan, dan pengangguran

#### 4. Klasifikasi berbasis konteks

- Dipakai dalam pipeline artikel untuk membantu klasifikasi tematik ekonomi

### Cara koneksi ke Gemini

Repo ini menggunakan **OpenAI-compatible endpoint** milik Google Gemini, bukan SDK Google terpisah.

Endpoint yang dipakai:

```text
https://generativelanguage.googleapis.com/v1beta/openai/
```

### Hal yang perlu diperhatikan

- Pastikan `GEMINI_API_KEY` aktif dan memiliki kuota.
- Karena dipakai untuk embedding dan generasi teks, biaya / rate limit perlu dipantau.
- Jika respons AI gagal, beberapa fitur akan fallback atau menampilkan pesan error aman.
- Embedding dan chat sangat bergantung pada kualitas data berita yang masuk.

## Penggunaan Web API BPS

Fitur statistik resmi memanfaatkan `clients/bps.py`.

### Data yang diambil

Sistem saat ini menyiapkan beberapa dataset resmi, termasuk:

- PDRB ADHK lapangan usaha
- PDRB ADHB lapangan usaha
- TPT dan TPAK
- Kemiskinan
- PDRB pengeluaran triwulanan ADHK
- PDRB pengeluaran triwulanan ADHB

### Kegunaan dalam aplikasi

- Ditampilkan pada dashboard statistik resmi
- Dipakai sebagai baseline dalam AI Insight
- Dipakai sebagai konteks tambahan saat AI Chat mendeteksi pertanyaan tentang statistik resmi

### Jika BPS API gagal

- Dashboard statistik resmi bisa kosong atau tidak lengkap
- AI insight/chat tetap bisa jalan dari berita, tetapi tanpa baseline resmi BPS

## Ringkasan Endpoint

Berikut ringkasan endpoint yang paling penting.

### Halaman

| Endpoint             | Fungsi               |
| -------------------- | -------------------- |
| `/login`           | Halaman login        |
| `/dashboard`       | Dashboard utama      |
| `/berita/<id>`     | Detail berita        |
| `/admin/users`     | Manajemen user admin |
| `/change-password` | Ganti password       |
| `/reset-password`  | Reset password       |

### Auth

| Endpoint                      | Method   | Fungsi                     |
| ----------------------------- | -------- | -------------------------- |
| `/api/login`                | `POST` | Login user                 |
| `/api/me`                   | `GET`  | Ambil info user aktif      |
| `/api/auth/change-password` | `POST` | Ganti password             |
| `/api/auth/reset-password`  | `POST` | Reset password dengan kode |
| `/logout`                   | `GET`  | Logout                     |

### Berita dan dashboard

| Endpoint                               | Method    | Fungsi                      |
| -------------------------------------- | --------- | --------------------------- |
| `/api/berita`                        | `GET`   | List berita dengan filter   |
| `/api/berita/<id>`                   | `GET`   | Detail berita               |
| `/api/berita/export`                 | `GET`   | Export berita               |
| `/api/berita/years`                  | `GET`   | List tahun yang tersedia    |
| `/api/dashboard/overview/summary`    | `GET`   | Ringkasan dashboard 30 hari |
| `/api/dashboard/data/filter-options` | `GET`   | Opsi filter dashboard       |
| `/api/berita/<id>/archive`           | `PATCH` | Arsip/pulihkan berita       |
| `/api/berita/<id>/classification`    | `PATCH` | Koreksi klasifikasi         |

### Scraping

| Endpoint                     | Method   | Fungsi                 |
| ---------------------------- | -------- | ---------------------- |
| `/api/scrape`              | `POST` | Trigger scraping       |
| `/api/scrape/progress`     | `GET`  | Progress scraping      |
| `/api/last-scrape`         | `GET`  | Info scraping terakhir |
| `/api/admin/backfill-kbli` | `POST` | Backfill KBLI manual   |

### AI

| Endpoint                    | Method   | Fungsi                      |
| --------------------------- | -------- | --------------------------- |
| `/api/ai-insights`        | `GET`  | Insight AI berbasis polling |
| `/api/ai-insights/stream` | `GET`  | Insight AI streaming SSE    |
| `/api/ai-chat/session`    | `POST` | Buat / ambil session chat   |
| `/api/ai-chat/history`    | `GET`  | Ambil riwayat chat          |
| `/api/ai-chat`            | `POST` | Chat non-stream             |
| `/api/ai-chat/stream`     | `POST` | Chat streaming SSE          |
| `/api/ai-chat/clear`      | `POST` | Bersihkan percakapan        |

### Statistik resmi

| Endpoint                     | Method  | Fungsi                    |
| ---------------------------- | ------- | ------------------------- |
| `/api/official-statistics` | `GET` | Ambil statistik resmi BPS |

## Perintah Penting

### Menjalankan aplikasi

```bash
python app.py
```

### Menjalankan scraper satu per satu

```bash
python -m scrapers.radartegal
python -m scrapers.panturapost
python -m scrapers.tribunjateng
python -m scrapers.kompas
python -m scrapers.setda_tegal
```

### Menjalankan script operasional

```bash
python -m scripts.users.create_user <username> <password> [role]
python -m scripts.backfill.backfill_kbli
python -m scripts.backfill.backfill_embeddings
python -m scripts.scraping.trigger_scrape --max-articles 150
python -m scripts.reference_data.build_kbli_embeddings
python -m scripts.reference_data.build_pdrb_pengeluaran_embeddings
python -m scripts.maintenance.clean_tags_db
```

## Data dan Database

Repo ini memakai Supabase Postgres

### Entitas

Beberapa tabel/domain yang terdeteksi dari repository dan service:

- `berita`
- `users`
- `password_reset_codes`
- `scrape_log`
- `ai_insights`
- session dan pesan AI chat
- `official_statistics_snapshots`

### Isi penting pada data berita

Setiap artikel minimal mengandung field berikut dalam pipeline:

- `title`
- `date`
- `date_parsed`
- `url`
- `content`
- `tags`
- `source`
- `kbli`
- `aktivitas_ekonomi`
- `pdrb_pengeluaran`
- `embedding`


## Scraper yang Digunakan

Sumber berita yang saat ini aktif:

- Radar Tegal
- Pantura Post
- Tribun Jateng
- Kompas
- Setda Tegal

### Kontrak scraper

Setiap scraper mengikuti pola umum:

```python
def scrape_new_articles(existing_urls: set, max_articles: int, on_progress=None) -> list[dict]:
    ...
```

## Developer

- **Feza Raffa Arnanda**
- **Faqih Indra Lesmana**
