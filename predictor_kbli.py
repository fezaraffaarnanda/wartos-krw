"""
Modul prediksi KBLI 2020 untuk integrasi Flask.

Penggunaan di Flask:
    from predictor_kbli import KBLIPredictor
    predictor = KBLIPredictor('model_kbli')

    # Prediksi satu teks
    hasil = predictor.prediksi("Petani meningkatkan produksi padi organik")

    # Prediksi batch
    hasil_batch = predictor.prediksi_batch(["teks 1", "teks 2"])
"""

import re
import os
import json
import joblib
import numpy as np


class KBLIPredictor:
    def __init__(self, model_dir='model_kbli'):
        """
        Load semua artefak model dari folder model_dir.
        """
        self.model = joblib.load(os.path.join(model_dir, 'model_terbaik.joblib'))
        self.vectorizer = joblib.load(os.path.join(model_dir, 'tfidf_vectorizer.joblib'))
        self.label_encoder = joblib.load(os.path.join(model_dir, 'label_encoder.joblib'))
        self.stopwords = joblib.load(os.path.join(model_dir, 'stopwords_gabungan.joblib'))
        self.kamus_normalisasi = joblib.load(os.path.join(model_dir, 'kamus_normalisasi.joblib'))

        with open(os.path.join(model_dir, 'metadata.json'), 'r') as f:
            self.metadata = json.load(f)

    # ---- Preprocessing (sama persis dengan notebook) ----

    def _bersihkan_teks(self, teks):
        if not teks or teks != teks:  # handle None / NaN
            return ''
        teks = str(teks)
        teks = re.sub(r'<[^>]+>', ' ', teks)
        teks = re.sub(r'http\S+|www\S+', '', teks)
        teks = re.sub(r'\S+@\S+', '', teks)
        teks = re.sub(r'@\w+', '', teks)
        teks = re.sub(r'#\w+', '', teks)
        teks = re.sub(r'\d+', '', teks)
        teks = re.sub(r'[^a-zA-Z\s]', ' ', teks)
        teks = re.sub(r'\s+', ' ', teks).strip()
        return teks

    def _case_folding(self, teks):
        return teks.lower()

    def _tokenize(self, teks):
        return teks.split() if isinstance(teks, str) else []

    def _hapus_stopword(self, tokens):
        return [kata for kata in tokens if kata not in self.stopwords and len(kata) > 2]

    def _normalisasi(self, tokens):
        if self.kamus_normalisasi:
            tokens = [self.kamus_normalisasi.get(kata, kata) for kata in tokens]
        return ' '.join(tokens)

    def preprocess(self, teks):
        """Jalankan seluruh pipeline preprocessing pada satu teks."""
        teks = self._bersihkan_teks(teks)
        teks = self._case_folding(teks)
        tokens = self._tokenize(teks)
        tokens = self._hapus_stopword(tokens)
        teks_bersih = self._normalisasi(tokens)
        return teks_bersih

    # ---- Prediksi ----

    def prediksi(self, teks, threshold=0.3):
        """
        Prediksi kategori KBLI dari satu teks berita.

        Returns:
            dict dengan keys:
                - kategori: kode kategori KBLI atau 'Tidak Relevan'
                - probabilitas: probabilitas tertinggi (0-1)
                - kandidat: kategori kandidat jika Tidak Relevan, else None
                - semua_probabilitas: dict {kategori: prob} untuk semua kelas
        """
        teks_bersih = self.preprocess(teks)
        X_input = self.vectorizer.transform([teks_bersih])
        proba = self.model.predict_proba(X_input)[0]

        idx_max = np.argmax(proba)
        prob_max = float(proba[idx_max])
        kategori_pred = self.label_encoder.inverse_transform([idx_max])[0]

        semua_prob = {
            self.label_encoder.inverse_transform([i])[0]: round(float(p), 4)
            for i, p in enumerate(proba)
        }
        # Urutkan dari probabilitas tertinggi
        semua_prob = dict(sorted(semua_prob.items(), key=lambda x: x[1], reverse=True))

        if prob_max < threshold:
            return {
                'kategori': 'Tidak Relevan',
                'probabilitas': round(prob_max, 4),
                'kandidat': kategori_pred,
                'semua_probabilitas': semua_prob,
            }
        return {
            'kategori': kategori_pred,
            'probabilitas': round(prob_max, 4),
            'kandidat': None,
            'semua_probabilitas': semua_prob,
        }

    def prediksi_batch(self, daftar_teks, threshold=0.3):
        """Prediksi untuk list of teks. Mengembalikan list of dict."""
        return [self.prediksi(teks, threshold) for teks in daftar_teks]

    def get_kelas(self):
        """Mengembalikan daftar semua kelas KBLI."""
        return list(self.label_encoder.classes_)


# ---- Contoh penggunaan langsung ----
if __name__ == '__main__':
    predictor = KBLIPredictor('model_kbli')

    print(f"Model: {predictor.metadata['model_terbaik']}")
    print(f"Kelas: {predictor.get_kelas()}")
    print()

    contoh = [
        "Petani di Jawa Tengah berhasil meningkatkan produksi padi dengan metode pertanian organik.",
        "Industri tekstil nasional mencatat lonjakan ekspor sebesar 12 persen.",
        "Hari ini cuaca cerah dan menyenangkan untuk berolahraga.",
        "Pemerintah Kabupaten (Pemkab) Tegal terus memperkuat sinergi dengan masyarakat melalui kegiatan Tarawih dan Silaturahim (Tarhim). Pada putaran ketiga yang berlangsung di Masjid Al-Hikmah, Desa Bojong, Kecamatan Bojong, Jumat (27/2/2026) malam, Sekretaris Daerah (Sekda) Kabupaten Tegal, Amir Makhmud, menyampaikan komitmen pemerintah dalam pemerataan pembangunan fisik maupun spiritual. kegiatan ini merupakan agenda rutin Pemerintah Kabupaten Tegal selama bulan suci Ramadhan ini dihadiri oleh,jajaran Forkopimda, para Kepala Organisasi Perangkat Daerah (OPD), Direktur RSUD Soeselo, Direktur RSUD Suradadi, jajaran Forkopimcam Bojong, serta tokoh agama dari PCNU dan Muhammadiyah. Kabupaten Tegal, tokoh agama, tokoh masyarakat, serta warga Bojong. Perwakilan tuan rumah sekaligus Takmir Masjid Al-Hikmah dalam sambutannya menyampaikan apresiasi mendalam atas kehadiran jajaran pemerintah dan Baznas Kabupaten Tegal. Pihaknya menyebut kunjungan ini sebagai bentuk perhatian nyata pemerintah terhadap warga, khususnya pascabencana banjir yang sempat melanda wilayah tersebut beberapa waktu lalu. Dalam kesempatan tersebut Takmir Masjid Al-Hikmah juga menyampaikan ucapan Terima kasih kepada Pemerintah Kabupaten Tegal bisa hadir dan bersilaturahmi di kecamatan Bojong"
        , "Ketegangan geopolitik di Timur Tengah mulai memukul sektor industri kreatif diKabupaten Tegal. Konflik antara Iran dan Israel serta blokade di jalur Laut Merah menyebabkaneksporSarung Tegalke pasarAfrikadan Timur Tengah tersendat total per Maret 2026.Dampak Konflik Global Terhadap IndustriSarung Tegal Sejumlah pengusaha sarung di sentra industri Talang melaporkan pembatalan pengiriman besar-besaran sejak dua hari terakhir. Jamal Alkatiri, pengusaha sarung Tegal mengonfirmasi bahwa jalur logistik internasional saat ini berada dalam posisi suspend. Mulai kemarin, pengiriman dari Indonesia ke Afrika terhenti. Kami mendapat kabar bahwa semua jadwal keberangkatan dibatalkan oleh pihak pelayaran, ujar Jamal saat ditemui di pabriknya, Desa Pacul, Senin 2 Maret 2026. Beberapa poin utama hambatan ekspor saat ini meliputi:Pembatalan Kontainer: Rencana pengiriman 50 ribu sarung (2 kontainer) pada 3 dan 7 Maret 2026 resmi dibatalkan.Kelangkaan Unit: Ketersediaan kontainer kosong di pelabuhan menurun drastis.Lonjakan Biaya: Ongkos transportasi logistik internasional naik signifikan sebesar 15% dalam satu bulan terakhir.Data Industri: Terdapat sekitar 30 perusahaan sarung di Kabupaten Tegal yang mayoritas produksinya menyasar pasar Afrika sebagai busana harian. Saat ini, para pengusaha hanya mampu memenuhi 30% dari total permintaan global akibat kendala distribusi dan situasi keamanan di Laut Merah yang melibatkan intervensi Amerika Serikat. Penjualan Domestik Jadi Penyelamat Jelang Lebaran 2026 Meski pasar ekspor lesu akibat imbasperang, para perajin bernapas lega berkat lonjakan permintaan di pasar domestik. Menjelang Idulfitri 2026, tren penjualan sarung di dalam negeri justru meroket tajam melalui platform marketplace. Jika biasanya kami menjual 20 hingga 50 sarung per hari, sekarang menembus 500 sarung per hari. Kenaikannya hampir 300%, ungkap Jamal. Produk unggulan seperti Sarung Toldem (Tenun Alat Tenun Bukan Mesin/ATBM) tetap menjadi primadona. Tekstur khas dan nilai tradisionalnya membuat permintaan lokal naik tiga kali lipat setiap memasuki musim Ramadan dan Lebaran.HarapanPelaku Usaha Hingga awal Maret 2026, pelaku usaha di Tegal hanya bisa menunggu kepastian stabilitas global. SARUNG TEGAL- Konflik Iran-Israel & Laut Merah menghambat ekspor 50 ribu Sarung Tegal ke Afrika. -Yeri Noveli- Imbasperangini dirasakan secara global. Kami berharap situasi segera membaik agar pembayaraneksporyang tertahan bisa segera dilunasi, pungkasnya."   
    ]



    for teks in contoh:
        hasil = predictor.prediksi(teks)
        print(f"Teks  : {teks[:80]}...")
        print(f"KBLI  : {hasil['kategori']}")
        print(f"Prob  : {hasil['probabilitas']*100:.1f}%")
        if hasil['kandidat']:
            print(f"Kand  : {hasil['kandidat']}")
        print()
