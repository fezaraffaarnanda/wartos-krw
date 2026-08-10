-- Submission feedback pengguna: rating 1-5, kategori, komentar opsional.
-- trigger_source membedakan tombol sidebar (selalu tersedia) dari
-- auto-prompt milestone (muncul sekali per snooze window).

create table if not exists public.feedback (
  id                    bigint      generated always as identity primary key,
  user_id               bigint      not null references public.users(id) on delete cascade,
  username              text        not null,
  role                  text        not null,
  rating                smallint    not null check (rating between 1 and 5),
  category              text        not null check (category in
                          ('berita', 'ai_chat', 'ai_insight', 'statistik_resmi', 'scraping', 'lainnya')),
  comment               text,
  page_path             text,
  event_count_at_submit integer     not null default 0,
  trigger_source        text        not null default 'sidebar'
                          check (trigger_source in ('sidebar', 'auto_prompt')),
  created_at            timestamptz not null default now()
);

comment on column public.feedback.username is
  'Disalin saat submit agar riwayat tetap terbaca bila user dihapus di kemudian hari.';

create index if not exists idx_feedback_created  on public.feedback (created_at desc);
create index if not exists idx_feedback_category on public.feedback (category, created_at desc);
create index if not exists idx_feedback_user     on public.feedback (user_id, created_at desc);
