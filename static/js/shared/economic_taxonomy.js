
const KBLI_KEY_MAPPING = {
  A:  "Pertanian, Kehutanan, dan Perikanan",
  B:  "Pertambangan dan Penggalian",
  C:  "Industri",
  D:  "Penyediaan Listrik, Gas, Uap/Air Panas, dan Udara Dingin",
  E:  "Penyediaan Air; Pengelolaan Air Limbah, Penanganan Limbah, dan Remediasi",
  F:  "Konstruksi",
  G:  "Perdagangan Besar dan Eceran",
  H:  "Transportasi dan Penyimpanan",
  I:  "Aktivitas Penyediaan Akomodasi dan Makan Minum",
  J:  "Aktivitas Penerbitan, Penyiaran, serta Produksi dan Distribusi Konten",
  K:  "Aktivitas Telekomunikasi, Pemrograman Komputer, Konsultansi, dan Jasa Informasi",
  L:  "Aktivitas Keuangan dan Asuransi",
  M:  "Aktivitas Real Estat",
  N:  "Aktivitas Profesional, Ilmiah, dan Teknis",
  O:  "Aktivitas Administratif dan Penunjang Usaha",
  P:  "Administrasi Pemerintahan dan Pertahanan, Serta Jaminan Sosial Wajib",
  Q:  "Pendidikan",
  R:  "Aktivitas Kesehatan Manusia dan Aktivitas Sosial",
  S:  "Kesenian, Olahraga, dan Rekreasi",
  T:  "Aktivitas Jasa Lainnya",
  U:  "Aktivitas Rumah Tangga sebagai Pemberi Kerja",
  V:  "Aktivitas Badan Internasional dan Badan Ekstra Internasional Lainnya",
  KE: "Kemiskinan",
  PG: "Pengangguran",
};

const AKTIVITAS_LABELS = {
  1:  "Kondisi perekonomian di kabupaten/kota secara umum",
  2:  "Aktivitas panen hasil tanaman pangan (padi, jagung, palawija)",
  3:  "Aktivitas panen hasil tanaman lainnya (perkebunan, hortikultura)",
  4:  "Aktivitas rumah potong hewan (RPH)",
  5:  "Aktivitas penangkapan/budidaya ikan laut dan darat",
  6:  "Aktivitas pertambangan non migas (batubara, bijih logam, dll)",
  7:  "Aktivitas penggalian (pasir, kerikil)",
  8:  "Aktivitas produksi CPO",
  9:  "Aktivitas industri makanan dan minuman selain CPO",
  10: "Aktivitas penjualan/penyaluran migas (BBM & LPG)",
  11: "Aktivitas penjualan dan reparasi mobil dan sepeda motor",
  12: "Aktivitas pengiriman barang/ekspedisi",
  13: "Aktivitas/keramaian di terminal bis/travel/pool",
  14: "Aktivitas usaha perhotelan",
  15: "Jumlah pengunjung rumah sakit, klinik, dan laboratorium kesehatan",
  16: "Aktivitas/transaksi jual beli di pasar tradisional",
  17: "Aktivitas/transaksi jual beli di mall/pusat perbelanjaan modern terbesar",
  18: "Banyaknya penyewaan ruang untuk berjualan di mall/supermarket (tenant)",
  19: "Aktivitas/keramaian pengunjung restoran dan rumah makan",
  20: "Jumlah pengunjung tempat wisata komersial",
  21: "Aktivitas penyaluran dana bantuan penanggulangan bencana oleh LNPRT",
  22: "Aktivitas partai politik (kampanye, kongres, musda, dll)",
  23: "Aktivitas perayaan kegiatan keagamaan",
  24: "Aktivitas pembangunan/renovasi besar-besaran rumah/tempat tinggal",
  25: "Aktivitas pembangunan gedung dan infrastruktur (jalan, jembatan, dll)",
  26: "Aktivitas pemberian bansos dari pemerintah",
  27: "Aktivitas bongkar muat di pelabuhan/bandara/stasiun",
};

const PDRB_PENGELUARAN_PARENT_LABELS = {
  PKRT: "Pengeluaran Konsumsi Rumah Tangga",
  PKP: "Pengeluaran Konsumsi Pemerintah",
  PMTB: "Pembentukan Modal Tetap Bruto",
  PKLNPRT: "Pengeluaran Konsumsi LNPRT",
  PI: "Perubahan Inventori",
};

const PDRB_PENGELUARAN_LABELS = {
  "PKRT-01": "Makanan dan minuman tidak beralkohol",
  "PKRT-02": "Minuman beralkohol, tembakau, dan narkotika",
  "PKRT-03": "Pakaian dan alas kaki",
  "PKRT-04": "Perumahan, air, listrik, gas, dan bahan bakar lainnya",
  "PKRT-05": "Furniture, perlengkapan rumah tangga, dan pemeliharaan rutin rumah",
  "PKRT-06": "Kesehatan",
  "PKRT-07": "Transportasi",
  "PKRT-08": "Komunikasi",
  "PKRT-09": "Rekreasi/hiburan dan kebudayaan",
  "PKRT-10": "Pendidikan",
  "PKRT-11": "Penyediaan makan minum dan penginapan/akomodasi",
  "PKRT-12": "Barang dan jasa lainnya",
  "PKP-01": "Pelayanan Umum",
  "PKP-02": "Pertahanan",
  "PKP-03": "Ketertiban dan Keamanan",
  "PKP-04": "Ekonomi",
  "PKP-05": "Perlindungan Lingkungan Hidup",
  "PKP-06": "Perumahan dan Fasilitas Umum",
  "PKP-07": "Kesehatan",
  "PKP-08": "Pariwisata dan Budaya",
  "PKP-09": "Agama",
  "PKP-10": "Pendidikan",
  "PKP-11": "Perlindungan Sosial",
  "PMTB-01": "Bangunan dan Tempat Tinggal",
  "PMTB-02": "Mesin dan Perlengkapan",
  "PMTB-03": "Aset Biologis yang Dibudidayakan",
  "PMTB-04": "Produk Kekayaan Intelektual",
  "PMTB-05": "Biaya Pemindahan Kepemilikan (Atas Aset Tidak Diproduksi)",
  "PKLNPRT-01": "Perumahan",
  "PKLNPRT-02": "Kesehatan",
  "PKLNPRT-03": "Rekreasi dan Kebudayaan",
  "PKLNPRT-04": "Pendidikan",
  "PKLNPRT-05": "Perlindungan Sosial",
  "PKLNPRT-06": "Keagamaan",
  "PKLNPRT-07": "Lingkungan Hidup",
  "PKLNPRT-08": "Partai Politik, Organisasi Buruh dan Profesional",
  "PKLNPRT-09": "Jasa Lainnya",
  "PI-01": "Bahan Baku dan Penolong",
  "PI-02": "Barang Dalam Proses (Work in Progress)",
  "PI-03": "Barang Jadi",
  "PI-04": "Barang untuk Dijual Kembali (Goods for Resale)",
};

const PDRB_PENGELUARAN_CODE_ORDER = Object.keys(PDRB_PENGELUARAN_LABELS).reduce(
  (acc, code, index) => {
    acc[code] = index;
    return acc;
  },
  {},
);

const KBLI_GROUP_CLASS = {
  A1: "a",
  A2: "a",
  A3: "a",
  B1: "b",
  B2: "b",
  B3: "b",
  B4: "b",
  C1: "c",
  C2: "c",
  C3: "c",
  C4: "c",
  C5: "c",
  D: "d",
  E: "e",
  F: "f",
  G: "g",
  H1: "h",
  H2: "h",
  H3: "h",
  H4: "h",
  H5: "h",
  I: "i",
  J: "j",
  K: "k",
  L: "l",
  MN: "mn",
  O: "o",
  P: "p",
  Q: "q",
  RSTU: "rstu",
  KE: "ke",
  PG: "pg",
};

function buildMasterFilterOptions() {
  const kbli_codes = Object.keys(KBLI_KEY_MAPPING);
  const aktivitas_codes = Object.keys(AKTIVITAS_LABELS).sort(
    (a, b) => Number(a) - Number(b),
  );
  const pdrb_pengeluaran_codes = Object.keys(PDRB_PENGELUARAN_LABELS).sort(
    (a, b) =>
      (PDRB_PENGELUARAN_CODE_ORDER[a] || 0) -
      (PDRB_PENGELUARAN_CODE_ORDER[b] || 0),
  );

  return { kbli_codes, aktivitas_codes, pdrb_pengeluaran_codes };
}

function _isKbliIrrelevant(kbli) {
  if (!kbli) return true;
  const k = kbli.trim();
  return k === "—" || k.toLowerCase().startsWith("tidak relevan");
}

function getPdrbPengeluaranParentCode(rawCode) {
  const normalized = String(rawCode || "").trim().toUpperCase();
  if (!normalized || normalized === "—" || normalized === "TIDAK RELEVAN") {
    return "";
  }
  const codeOnly = normalized.split("/", 1)[0];
  const dashIndex = codeOnly.indexOf("-");
  return dashIndex === -1 ? "" : codeOnly.slice(0, dashIndex);
}
