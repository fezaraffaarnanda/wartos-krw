-- Sebelumnya nol index pada relevance_score/human_label/classifier_model,
-- padahal review-queue mengurutkan berdasarkan itu dan confusion-matrix
-- men-scan penuh -- tak terasa di 4.8k baris tapi tumbuh linear.

create index if not exists idx_berita_relevance_score
  on public.berita (relevance_score) where relevance_score is not null;

create index if not exists idx_berita_relevance_uncertainty
  on public.berita (relevance_uncertainty, id)
  where human_label is null and relevance_score is not null;

create index if not exists idx_berita_human_label
  on public.berita (human_label) where human_label is not null;

-- Ini yang di-scan backfill relevance versi baru (predikat checked_at IS NULL
-- menggantikan is_relevant IS NULL yang tidak pernah menjaring baris fail-open).
create index if not exists idx_berita_relevance_unchecked
  on public.berita (id) where relevance_checked_at is null;

create index if not exists idx_berita_label_source
  on public.berita (label_source) where label_source is not null;

create index if not exists idx_berita_prompt_version
  on public.berita (relevance_prompt_version) where relevance_prompt_version is not null;
