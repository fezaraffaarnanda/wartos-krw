-- Kolom tindak lanjut admin atas masukan pengguna.
--
-- Isi masukan (rating, kategori, komentar) sengaja TIDAK dibuat bisa diedit:
-- itu kesaksian pengguna. Yang bisa diubah admin hanyalah status penanganan
-- dan catatan internal di kolom terpisah.

alter table public.feedback
  add column if not exists status text not null default 'baru'
    check (status in ('baru', 'dibaca', 'ditindaklanjuti')),
  add column if not exists admin_note text,
  add column if not exists handled_by text,
  add column if not exists handled_at timestamptz;

comment on column public.feedback.status is
  'Alur tindak lanjut admin: baru -> dibaca -> ditindaklanjuti.';
comment on column public.feedback.admin_note is
  'Catatan internal admin. Tidak pernah ditampilkan ke pengirim masukan.';

create index if not exists idx_feedback_status on public.feedback (status, created_at desc);
