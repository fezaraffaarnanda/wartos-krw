-- Catch-up: kolom relevance di `berita` dan tabel `relevance_prompts` tidak
-- pernah punya migrasi -- keduanya hanya ada di Supabase live. Migrasi ini
-- idempoten sehingga environment baru bisa di-provision langsung dari repo.
-- Di production (yang sudah punya kolom/tabel ini) migrasi ini adalah no-op.

alter table public.berita
  add column if not exists is_relevant      boolean,
  add column if not exists relevance_score  smallint,
  add column if not exists relevance_reason text,
  add column if not exists classifier_model text,
  add column if not exists human_label      boolean,
  add column if not exists human_labeled_at timestamptz,
  add column if not exists human_labeled_by text;

comment on column public.berita.is_relevant is
  'Keputusan gerbang tahap-1 (classifier relevance): true = layak diklasifikasi lanjut.';
comment on column public.berita.relevance_score is
  '0-100 dari rubrik 4 kriteria. NULL = classifier gagal (fail-open, lihat relevance_checked_at).';
comment on column public.berita.human_label is
  'Keputusan manusia (admin) apakah berita relevan secara ekonomi. NULL = belum dilabeli.';
comment on column public.berita.human_labeled_at is
  'Waktu admin memberikan label manual.';
comment on column public.berita.human_labeled_by is
  'Username admin yang memberi label.';

create table if not exists public.relevance_prompts (
  id          bigint      generated always as identity primary key,
  version     text        not null unique,
  prompt_text text        not null,
  created_by  text,
  notes       text,
  is_active   boolean     not null default false,
  created_at  timestamptz not null default now()
);

create unique index if not exists one_active_prompt
  on public.relevance_prompts (is_active) where is_active;

-- Seed rel-v1: teks persis SYSTEM_PROMPT di ai/relevance.py saat migrasi ini
-- dibuat. Hanya berlaku untuk environment baru -- di production rel-v1 sudah
-- ada (di-seed manual 2026-07-03), jadi ON CONFLICT DO NOTHING membuat baris
-- ini no-op di sana.
insert into public.relevance_prompts (version, prompt_text, created_by, notes, is_active)
values (
  'rel-v1',
  $prompt$Kamu adalah filter awal untuk berita ekonomi daerah Karawang. Tugasmu menilai apakah sebuah berita LAYAK dianalisis lebih lanjut untuk klasifikasi ekonomi (KBLI, aktivitas ekonomi, PDRB), atau harus dibuang karena tidak berbobot.

Konteks: Sistem ini membantu BPS memetakan aktivitas ekonomi dari pemberitaan lokal. Berita yang "berbobot" adalah yang mengandung sinyal ekonomi nyata — bukan seremoni, bukan politik murni, bukan kriminal, bukan human-interest.

Nilai berita berdasarkan 4 kriteria berikut (total 100 poin):

1. ANGKA EKONOMI KONKRET (0-30)
   Ada nilai investasi, omzet, jumlah tenaga kerja, volume produksi, nilai ekspor/impor, harga, atau target kuantitatif. Makin spesifik angkanya, makin tinggi skornya. Tanpa angka sama sekali → maksimal 10.

2. ENTITAS USAHA TERIDENTIFIKASI (0-25)
   Menyebut perusahaan, pabrik, kawasan industri, UMKM, koperasi, komoditas, atau sektor usaha spesifik. Bukan sekadar "pemerintah" atau "masyarakat". Seremoni tanpa entitas usaha nyata → rendah.

3. DAMPAK PRODUKSI/DISTRIBUSI/KONSUMSI (0-25)
   Berita menggambarkan aktivitas ekonomi riil: produksi naik/turun, pasar dibuka, distribusi terganggu, daya beli berubah, lapangan kerja. Bukan sekadar peresmian simbolis, kunjungan pejabat, atau wacana.

4. SKALA DAMPAK (0-20)
   Lokal kecil/individual → rendah. Berpengaruh ke satu sektor, banyak pelaku, atau skala kabupaten → tinggi.

PANDUAN KEPUTUSAN:
- score >= 50  → relevan (layak dianalisis lanjut)
- score < 50   → tidak relevan (dibuang)

Berita BORDERLINE (score 40-59) wajib diberi alasan jelas agar bisa direview manual.

Contoh TIDAK RELEVAN: berita kecelakaan, kegiatan keagamaan, lomba, pelantikan pejabat tanpa konteks ekonomi, imbauan umum, cuaca, kriminal.

Contoh RELEVAN: pabrik baru investasi Rp X, panen raya komoditas Y sekian ton, PHK di sektor Z, harga bahan pokok naik, ekspor produk lokal, pertumbuhan UMKM.

Balas HANYA dalam format JSON valid:
{
  "score": <integer 0-100>,
  "is_relevant": <true|false>,
  "reason": "<1-2 kalimat alasan, sebut kriteria mana yang terpenuhi/tidak>"
}$prompt$,
  'system-seed',
  'Seed awal dari konstanta kode.',
  true
)
on conflict (version) do nothing;
