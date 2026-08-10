-- Counter agregat pemakaian fitur per user, dipakai memicu prompt feedback.
-- Satu row per user (bukan append-only) -- 8 user, konsumen cuma
-- event_count >= 10, dan read-modify-write dari Python akan race antar tab
-- kalau tidak lewat RPC atomik.
--
-- Angka BERASAL DARI KLIEN (static/js/shared/activity.js), bukan diukur
-- server. Kolom ini HANYA dipakai menentukan kapan modal feedback muncul --
-- bukan produk analitik/audit pemakaian.

create table if not exists public.user_activity_state (
  user_id               bigint      primary key references public.users(id) on delete cascade,
  event_count           integer     not null default 0,
  counts                jsonb       not null default '{}'::jsonb,
  first_event_at        timestamptz,
  last_event_at         timestamptz,
  first_login_at        timestamptz,
  prompt_snoozed_until  timestamptz,
  prompt_dismiss_count  smallint    not null default 0,
  feedback_submitted_at timestamptz,
  updated_at            timestamptz not null default now()
);

comment on table public.user_activity_state is
  'Satu row per user. Counter agregat pemakaian fitur untuk memicu prompt feedback. Bukan tabel analitik -- angka berasal dari klien dan hanya dipakai untuk timing modal.';

create index if not exists idx_user_activity_state_prompt
  on public.user_activity_state (prompt_snoozed_until) where feedback_submitted_at is null;

-- first_login_at di-seed dari users.created_at pada increment pertama --
-- 8 akun existing sudah lama, jadi syarat "3 hari sejak login pertama"
-- langsung terpenuhi dan milestone menyusut ke syarat event_count saja.
create or replace function public.bump_user_activity(p_user_id bigint, p_event_type text)
returns public.user_activity_state
language plpgsql as $$
declare v_row public.user_activity_state;
begin
  insert into public.user_activity_state as s
    (user_id, event_count, counts, first_event_at, last_event_at, first_login_at)
  values
    (p_user_id, 1, jsonb_build_object(p_event_type, 1), now(), now(),
     (select created_at from public.users where id = p_user_id))
  on conflict (user_id) do update
     set event_count    = s.event_count + 1,
         counts         = s.counts || jsonb_build_object(
                             p_event_type,
                             coalesce((s.counts ->> p_event_type)::int, 0) + 1),
         first_event_at = coalesce(s.first_event_at, now()),
         last_event_at  = now(),
         first_login_at = coalesce(s.first_login_at,
                             (select created_at from public.users where id = p_user_id)),
         updated_at     = now()
  returning * into v_row;
  return v_row;
end;
$$;
