-- Migrasi: tambah kolom source ke tabel berita
-- Jalankan di Supabase SQL Editor jika tabel sudah ada sebelumnya

ALTER TABLE berita ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'Radar Tegal';
