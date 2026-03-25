alter table public.berita
add column if not exists is_archived boolean not null default false,
add column if not exists archived_at timestamp with time zone;

create index if not exists idx_berita_is_archived_date_parsed
on public.berita (is_archived, date_parsed desc);
