-- Batasi sampel audit ke sumber berita wilayah fokus.
--
-- Versi 20260815 menarik acak dari SELURUH tabel `berita`, termasuk 1.859 baris
-- warisan wilayah lama yang sengaja tetap disimpan. Akibatnya sampel yang justru
-- dipakai sebagai "estimasi tak bias" tercemar wilayah lain.
--
-- Daftar sumber dikirim sebagai parameter, bukan dihardcode di SQL, supaya
-- config/region.py tetap satu-satunya sumber kebenaran wilayah.

-- Overload lama harus dibuang dulu: menambah parameter berdefault akan membuat
-- dua fungsi bernama sama dan PostgREST menolak panggilan yang ambigu.
drop function if exists public.draw_relevance_audit_sample(text, integer, text);

create or replace function public.draw_relevance_audit_sample(
  p_batch_key  text,
  p_per_band   integer,
  p_created_by text,
  p_sources    text[] default null
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
       and (p_sources is null or b.source = any(p_sources))
  ), picked as (
    select id, band, row_number() over (partition by band order by random()) as rn
      from banded
  )
  insert into public.relevance_audit_items (batch_id, berita_id, band)
  select v_batch_id, id, band from picked where rn <= p_per_band;

  -- Populasi per band dihitung atas SELURUH row berskor (termasuk yang sudah
  -- dilabeli), karena bobot strata metrik = population / labeled_in_band.
  -- Batasan sumber tetap berlaku di sini: bobot harus sepopulasi dengan sampel.
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
       where b.relevance_score is not null
         and b.is_archived = false
         and (p_sources is null or b.source = any(p_sources))
       group by 1
    ) t;

  update public.relevance_audit_batches
     set band_plan = coalesce(v_plan, '{}'::jsonb)
   where id = v_batch_id;

  return v_batch_id;
end;
$$;
