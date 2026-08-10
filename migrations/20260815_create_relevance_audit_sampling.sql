-- Sampel audit acak berstrata: satu-satunya sumber metrik precision/recall
-- yang TIDAK bias. Label dari antrian Prioritas/uncertainty datang dari band
-- skor yang paling meragukan -- representatif untuk few-shot, tapi bukan
-- estimasi performa korpus. Sampel ini menarik n item per band skor secara
-- acak supaya setiap band terwakili proporsional terhadap populasinya.

create table if not exists public.relevance_audit_batches (
  id          bigint      generated always as identity primary key,
  batch_key   text        not null unique,
  target_size integer     not null,
  band_plan   jsonb       not null default '{}'::jsonb,
  status      text        not null default 'open' check (status in ('open', 'closed')),
  created_by  text,
  created_at  timestamptz not null default now(),
  closed_at   timestamptz
);

create table if not exists public.relevance_audit_items (
  id         bigint      generated always as identity primary key,
  batch_id   bigint      not null references public.relevance_audit_batches(id) on delete cascade,
  berita_id  bigint      not null references public.berita(id) on delete cascade,
  band       text        not null,
  labeled_at timestamptz,
  unique (batch_id, berita_id)
);

comment on table public.relevance_audit_batches is
  'Satu batch = satu tarikan sampel acak berstrata untuk audit tak bias.';
comment on column public.relevance_audit_batches.band_plan is
  'jsonb {band: {population, sampled}} -- populasi dipakai bobot strata saat menghitung metrik tak bias.';

create index if not exists idx_rel_audit_items_open
  on public.relevance_audit_items (batch_id, labeled_at nulls first);

-- RPC: fluent API Supabase tidak bisa ORDER BY random(), jadi sampling
-- berstrata harus lewat function. p_per_band item diambil acak dari tiap
-- band skor (0-19, 20-39, 40-59, 60-79, 80-100) di antara baris yang sudah
-- berskor dan belum dilabeli manusia.
create or replace function public.draw_relevance_audit_sample(
  p_batch_key  text,
  p_per_band   integer,
  p_created_by text
) returns bigint
language plpgsql as $$
declare
  v_batch_id bigint;
  v_plan     jsonb;
begin
  insert into public.relevance_audit_batches (batch_key, target_size, created_by)
  values (p_batch_key, p_per_band * 5, p_created_by)
  returning id into v_batch_id;

  with banded as (
    select b.id,
           case when b.relevance_score between  0 and 19 then 'b00_19'
                when b.relevance_score between 20 and 39 then 'b20_39'
                when b.relevance_score between 40 and 59 then 'b40_59'
                when b.relevance_score between 60 and 79 then 'b60_79'
                else 'b80_100' end as band
      from public.berita b
     where b.relevance_score is not null
       and b.human_label is null
       and b.is_archived = false
  ), picked as (
    select id, band, row_number() over (partition by band order by random()) as rn
      from banded
  )
  insert into public.relevance_audit_items (batch_id, berita_id, band)
  select v_batch_id, id, band from picked where rn <= p_per_band;

  -- Populasi per band dihitung atas SELURUH row berskor (termasuk yang sudah
  -- dilabeli), karena bobot strata metrik = population / labeled_in_band.
  select jsonb_object_agg(band, jsonb_build_object('population', pop, 'sampled', smp))
    into v_plan
    from (
      select case when b.relevance_score between  0 and 19 then 'b00_19'
                  when b.relevance_score between 20 and 39 then 'b20_39'
                  when b.relevance_score between 40 and 59 then 'b40_59'
                  when b.relevance_score between 60 and 79 then 'b60_79'
                  else 'b80_100' end as band,
             count(*) as pop,
             count(*) filter (where exists (
               select 1 from public.relevance_audit_items i
                where i.batch_id = v_batch_id and i.berita_id = b.id
             )) as smp
        from public.berita b
       where b.relevance_score is not null and b.is_archived = false
       group by 1
    ) t;

  update public.relevance_audit_batches
     set band_plan = coalesce(v_plan, '{}'::jsonb)
   where id = v_batch_id;

  return v_batch_id;
end;
$$;
