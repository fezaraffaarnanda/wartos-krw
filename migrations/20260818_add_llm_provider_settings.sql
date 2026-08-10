-- Toggle provider LLM default (Gemini/DeepSeek) dari admin panel tanpa redeploy.
-- Single-row config table (id terkunci ke 1). build_chat_client() di clients/llm.py
-- baca provider aktif dari sini (dengan TTL cache), fallback ke key-presence lama
-- kalau row belum ada / provider yang dipilih key-nya kosong.

create table if not exists public.llm_provider_settings (
    id         smallint    primary key default 1 check (id = 1),
    provider   text        not null check (provider in ('deepseek', 'gemini')),
    updated_by text,
    updated_at timestamptz not null default now()
);

comment on table public.llm_provider_settings is
    'Config single-row: provider LLM default (deepseek/gemini) yang dipakai build_chat_client(). Diubah dari /admin/llm.';

insert into public.llm_provider_settings (id, provider, updated_by)
values (1, 'deepseek', 'migration')
on conflict (id) do nothing;
