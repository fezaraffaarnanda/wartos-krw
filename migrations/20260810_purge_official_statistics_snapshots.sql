-- Wilayah fokus berpindah dari Kabupaten Tegal (domain 3328) ke Kabupaten
-- Karawang (domain 3215). Snapshot lama berisi angka Kab. Tegal DAN memakai
-- kunci payload lama (`tegal_metrics`), sehingga akan terus disajikan di bawah
-- brand baru karena `_read_persisted` dibaca sebelum panggilan Web API BPS.
--
-- Hapus seluruh isi agar dibangun ulang dari Web API BPS pada request berikutnya.
-- Aman: tabel ini murni cache, bukan sumber data.
delete from public.official_statistics_snapshots;
