-- Catat token usage tiap panggilan LLM (relevance/kbli/aktivitas/pdrb/chat/insights/
-- prompt_draft) supaya bisa dibandingkan konsumsi DeepSeek vs Gemini per fitur.
-- Forward-only -- tidak ada data historis sebelum tabel ini ada karena response.usage
-- sebelumnya dibuang begitu saja di semua call site.

create table if not exists public.llm_usage_log (
    id               bigserial   primary key,
    created_at       timestamptz not null default now(),
    feature          text        not null,
    provider         text        not null,
    model            text        not null,
    prompt_tokens    integer,
    completion_tokens integer,
    total_tokens     integer,
    latency_ms       integer,
    success          boolean     not null default true,
    error            text
);

comment on table public.llm_usage_log is
    'Log token usage per panggilan LLM. Diisi best-effort oleh clients/llm.py -- kegagalan insert tidak boleh menggagalkan fitur utama.';
comment on column public.llm_usage_log.feature is
    'relevance | kbli | aktivitas | pdrb | chat | insights | prompt_draft';

create index if not exists idx_llm_usage_log_created_at
  on public.llm_usage_log (created_at);

create index if not exists idx_llm_usage_log_feature_provider
  on public.llm_usage_log (feature, provider);
