-- Tabel berita untuk project "Crawl Berita BPS"
-- Jalankan SQL ini di Supabase SQL Editor

CREATE TABLE IF NOT EXISTS berita (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    date TEXT,
    url TEXT UNIQUE NOT NULL,
    content TEXT,
    tags TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_berita_url ON berita (url);
