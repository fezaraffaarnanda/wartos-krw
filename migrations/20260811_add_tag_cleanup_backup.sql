-- Snapshot tag asli sebelum pembersihan destruktif (utils.tags.clean_tags).
-- Diisi oleh: python -m scripts.maintenance.clean_tags_db --apply --snapshot
-- Dipakai juga sebagai worklist re-embedding (hanya baris yang benar-benar
-- berubah yang perlu di-embed ulang) oleh
-- scripts/maintenance/reembed_after_tag_cleanup.py (menyusul terpisah).
-- Aman di-DROP setelah hasil pembersihan diterima.

create table if not exists public.tag_cleanup_backup (
    berita_id   bigint      primary key references public.berita(id) on delete cascade,
    tags_before text        not null,
    tags_after  text        not null,
    rules_hit   text        not null default '',
    created_at  timestamptz not null default now()
);

comment on table public.tag_cleanup_backup is
    'Backup satu kali kolom berita.tags sebelum clean_tags dijalankan via --apply. Boleh di-drop setelah verifikasi.';
comment on column public.tag_cleanup_backup.rules_hit is
    'CSV alasan tag dibuang untuk baris ini, mis. "sumber,pejabat" — lihat utils.tags.DROP_REASONS.';
