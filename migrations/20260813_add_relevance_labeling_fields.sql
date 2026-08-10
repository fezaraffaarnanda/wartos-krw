-- Kolom baru untuk redesign audit relevance:
--   relevance_checked_at  : watermark klasifikasi. Diisi HANYA saat classifier
--                            berhasil menghasilkan skor -- ini yang membuat 555
--                            baris fail-open (relevance_score NULL, is_relevant
--                            true) terjangkau lagi oleh backfill.
--   relevance_attempts    : jumlah percobaan (berhasil maupun gagal). Backfill
--                            berhenti retry baris yang gagal permanen.
--   relevance_prompt_version : versi prompt saat baris diklasifikasi, dipisah
--                            dari classifier_model agar bisa di-index & di-JOIN.
--   label_source           : 'audit' (sampel acak berstrata, dipakai metrik tak
--                            bias) vs 'targeted' (antrian uncertainty/failed,
--                            bias, few-shot saja) vs 'failure_triage'/'import'.
--   relevance_uncertainty  : abs(score-50), generated column. Antrian Prioritas
--                            di-order dari sini, menggantikan filter borderline
--                            40-59 yang membuat item yang salah dengan percaya
--                            diri (skor 90 tapi keliru) tidak pernah terlihat.

alter table public.berita
  add column if not exists relevance_checked_at     timestamptz,
  add column if not exists relevance_attempts       smallint not null default 0,
  add column if not exists relevance_prompt_version text,
  add column if not exists label_source             text,
  add column if not exists human_label_note         text;

alter table public.berita
  add column if not exists relevance_uncertainty smallint
  generated always as (abs(relevance_score - 50)) stored;

comment on column public.berita.relevance_checked_at is
  'Diisi HANYA saat classifier berhasil menghasilkan skor. NULL = belum pernah berhasil diklasifikasi (termasuk fail-open).';
comment on column public.berita.relevance_attempts is
  'Jumlah percobaan klasifikasi (berhasil maupun gagal). Dipakai backfill untuk berhenti retry baris rusak permanen.';
comment on column public.berita.label_source is
  'audit = dari sampel acak berstrata (dipakai untuk metrik tak bias). targeted = dari antrian uncertainty/failed (bias, few-shot saja).';

alter table public.berita drop constraint if exists berita_label_source_check;
alter table public.berita add constraint berita_label_source_check
  check (label_source is null or label_source in ('audit', 'targeted', 'failure_triage', 'import'));

-- Backfill: baris yang sudah punya skor dianggap sudah pernah berhasil dicek.
-- Baris tanpa skor (fail-open) SENGAJA DIBIARKAN relevance_checked_at NULL,
-- itulah yang menjadikannya target retry backfill baru.
update public.berita
   set relevance_checked_at = coalesce(relevance_checked_at, created_at, now()),
       relevance_attempts   = greatest(relevance_attempts, 1)
 where relevance_score is not null
   and relevance_checked_at is null;

update public.berita
   set relevance_prompt_version = nullif(split_part(classifier_model, '/', 2), '')
 where classifier_model is not null
   and relevance_prompt_version is null;

-- Label existing berasal dari tab Borderline lama (antrian bias), tandai
-- targeted -- konsisten dengan bagaimana label itu sesungguhnya terkumpul.
update public.berita
   set label_source = 'targeted'
 where human_label is not null
   and label_source is null;
