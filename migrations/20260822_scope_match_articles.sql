-- Batasi retrieval RAG (AI Chat + AI Insights) lewat parameter.
--
-- Versi lama hanya menyaring embedding, ambang similarity, dan tanggal, jadi
-- tiap pertanyaan mengambil 10 teratas dari SELURUH tabel berita: termasuk
-- 1.859 baris warisan wilayah lama dan 6.323 baris yang ditolak gerbang
-- relevansi (kriminal, kecelakaan, seremonial). Jawaban chat karena itu bisa
-- menganalisis wilayah yang salah atau mengutip berita kriminal sebagai bukti
-- ekonomi.
--
-- Default dibuat permisif supaya tidak ada pemanggil yang berubah perilaku
-- diam-diam; yang menentukan batasan adalah pemanggilnya (ai/chat.py).

drop function if exists public.match_articles(vector, integer, double precision, date, date);

create or replace function public.match_articles(
  query_embedding  vector,
  match_count      integer default 30,
  match_threshold  double precision default 0.1,
  filter_date_from date default null,
  filter_date_to   date default null,
  filter_sources   text[] default null,
  only_relevant    boolean default false,
  exclude_archived boolean default false
)
 returns table(id bigint, title text, date text, url text, content text, tags text, source text, date_parsed date, kbli text, similarity double precision)
 language plpgsql
 security definer
 set search_path to 'public', 'extensions'
as $function$
begin
  return query
  select
    b.id,
    b.title,
    b.date,
    b.url,
    b.content,
    b.tags,
    b.source,
    b.date_parsed,
    b.kbli,
    (1 - (b.embedding <=> query_embedding))::float as similarity
  from public.berita b
  where
    b.embedding is not null
    and (1 - (b.embedding <=> query_embedding)) >= match_threshold
    and (filter_date_from is null or b.date_parsed >= filter_date_from)
    and (filter_date_to   is null or b.date_parsed <= filter_date_to)
    and (filter_sources   is null or b.source = any(filter_sources))
    and (not only_relevant    or b.is_relevant is not false)
    and (not exclude_archived or b.is_archived = false)
  order by b.embedding <=> query_embedding
  limit match_count;
end;
$function$;
