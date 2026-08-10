-- Riwayat label append-only. Memungkinkan undo lintas reload (server-side,
-- bukan cuma stack di memori browser), provenance per label, dan metrik
-- per-versi-prompt yang bertahan meski baris yang sama diklasifikasi ulang.
-- Volume tetap kecil -- label datang di kecepatan manusia, bukan mesin.

create table if not exists public.relevance_label_events (
  id             bigint      generated always as identity primary key,
  berita_id      bigint      not null references public.berita(id) on delete cascade,
  previous_label boolean,
  new_label      boolean,
  label_source   text        not null default 'targeted',
  note           text,
  machine_label  boolean,
  machine_score  smallint,
  prompt_version text,
  actor_username text        not null,
  created_at     timestamptz not null default now()
);

comment on table public.relevance_label_events is
  'Riwayat setiap perubahan human_label pada berita. Dipakai untuk undo, audit trail, dan metrik per versi prompt.';
comment on column public.relevance_label_events.new_label is
  'NULL berarti label dihapus (undo/clear), bukan diset ke false.';

create index if not exists idx_rel_label_events_berita
  on public.relevance_label_events (berita_id, created_at desc);
create index if not exists idx_rel_label_events_actor
  on public.relevance_label_events (actor_username, created_at desc);
create index if not exists idx_rel_label_events_created
  on public.relevance_label_events (created_at desc);
