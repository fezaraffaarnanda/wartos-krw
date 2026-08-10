-- Perbaiki aktivasi prompt non-transaksional: insert_and_activate() Python
-- lama menonaktifkan lalu insert dalam dua statement terpisah -- kalau insert
-- gagal, tersisa NOL prompt aktif dan setiap worker diam-diam kembali ke
-- SYSTEM_PROMPT hardcoded di kode sambil tetap menandai baris dengan versi
-- baru. RPC di sini menjadikan aktivasi satu transaksi implisit plpgsql.

alter table public.relevance_prompts
  add column if not exists activated_at   timestamptz,
  add column if not exists deactivated_at timestamptz,
  add column if not exists parent_version text,
  add column if not exists eval_json      jsonb not null default '{}'::jsonb,
  add column if not exists status         text  not null default 'archived';

update public.relevance_prompts
   set status = 'active', activated_at = coalesce(activated_at, created_at)
 where is_active;

alter table public.relevance_prompts drop constraint if exists relevance_prompts_status_check;
alter table public.relevance_prompts add constraint relevance_prompts_status_check
  check (status in ('draft', 'active', 'archived'));

comment on column public.relevance_prompts.eval_json is
  'Hasil dry-run eval (precision/recall/F1 draft vs aktif) yang menjadi dasar aktivasi versi ini.';

create or replace function public.activate_relevance_prompt(
  p_version     text,
  p_prompt_text text,
  p_created_by  text,
  p_notes       text  default '',
  p_eval        jsonb default '{}'::jsonb,
  p_parent      text  default null
) returns public.relevance_prompts
language plpgsql as $$
declare v_row public.relevance_prompts;
begin
  update public.relevance_prompts
     set is_active = false, status = 'archived', deactivated_at = now()
   where is_active;

  insert into public.relevance_prompts
    (version, prompt_text, created_by, notes, is_active, status, activated_at, eval_json, parent_version)
  values
    (p_version, p_prompt_text, p_created_by, coalesce(p_notes, ''), true, 'active', now(),
     coalesce(p_eval, '{}'::jsonb), p_parent)
  on conflict (version) do update
     set prompt_text    = excluded.prompt_text,
         is_active      = true,
         status         = 'active',
         activated_at   = now(),
         deactivated_at = null,
         eval_json      = excluded.eval_json
  returning * into v_row;

  return v_row;
end;
$$;

create or replace function public.rollback_relevance_prompt(p_version text)
returns public.relevance_prompts
language plpgsql as $$
declare v_row public.relevance_prompts;
begin
  if not exists (select 1 from public.relevance_prompts where version = p_version) then
    raise exception 'Versi prompt % tidak ditemukan', p_version;
  end if;

  update public.relevance_prompts
     set is_active = false, status = 'archived', deactivated_at = now()
   where is_active and version <> p_version;

  update public.relevance_prompts
     set is_active = true, status = 'active', activated_at = now(), deactivated_at = null
   where version = p_version
  returning * into v_row;

  return v_row;
end;
$$;
