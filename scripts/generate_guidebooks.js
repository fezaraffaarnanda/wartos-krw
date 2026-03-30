const fs = require("fs");
const path = require("path");
const {
  AlignmentType,
  Document,
  Footer,
  HeadingLevel,
  ImageRun,
  LevelFormat,
  Packer,
  PageBreak,
  PageNumber,
  Paragraph,
  TableOfContents,
  TextRun,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const LOGO_PATH = path.join(ROOT, "static", "favicon.png");

const numbering = {
  config: [
    {
      reference: "bullet-list",
      levels: [
        {
          level: 0,
          format: LevelFormat.BULLET,
          text: "•",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        },
      ],
    },
    {
      reference: "num-1",
      levels: [
        {
          level: 0,
          format: LevelFormat.DECIMAL,
          text: "%1.",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        },
      ],
    },
    {
      reference: "num-2",
      levels: [
        {
          level: 0,
          format: LevelFormat.DECIMAL,
          text: "%1.",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        },
      ],
    },
    {
      reference: "num-3",
      levels: [
        {
          level: 0,
          format: LevelFormat.DECIMAL,
          text: "%1.",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        },
      ],
    },
    {
      reference: "num-4",
      levels: [
        {
          level: 0,
          format: LevelFormat.DECIMAL,
          text: "%1.",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        },
      ],
    },
    {
      reference: "num-5",
      levels: [
        {
          level: 0,
          format: LevelFormat.DECIMAL,
          text: "%1.",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        },
      ],
    },
    {
      reference: "num-6",
      levels: [
        {
          level: 0,
          format: LevelFormat.DECIMAL,
          text: "%1.",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        },
      ],
    },
  ],
};

function formatTanggalIndonesia(date = new Date()) {
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(date);
}

function run(text, options = {}) {
  return new TextRun({
    text,
    font: options.font || "Arial",
    size: options.size || 24,
    bold: options.bold || false,
    italics: options.italics || false,
    color: options.color || "1F2937",
  });
}

function p(text, options = {}) {
  return new Paragraph({
    alignment: options.alignment || AlignmentType.JUSTIFIED,
    spacing: options.spacing || { after: 140, line: 360 },
    heading: options.heading,
    children: [run(text, options.run || {})],
  });
}

function richParagraph(chunks, options = {}) {
  return new Paragraph({
    alignment: options.alignment || AlignmentType.JUSTIFIED,
    spacing: options.spacing || { after: 140, line: 360 },
    children: chunks.map((chunk) =>
      run(chunk.text, {
        bold: chunk.bold,
        italics: chunk.italics,
        size: chunk.size,
        color: chunk.color,
      }),
    ),
  });
}

function bulletList(items) {
  return items.map(
    (item) =>
      new Paragraph({
        numbering: { reference: "bullet-list", level: 0 },
        spacing: { after: 90, line: 320 },
        children: [run(item)],
      }),
  );
}

function numberedList(items, reference) {
  return items.map(
    (item) =>
      new Paragraph({
        numbering: { reference, level: 0 },
        spacing: { after: 90, line: 320 },
        children: [run(item)],
      }),
  );
}

function coverPage(title, subtitle, dateText) {
  const logoData = fs.readFileSync(LOGO_PATH);
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 400, after: 220 },
      children: [
        new ImageRun({
          type: "png",
          data: logoData,
          transformation: { width: 95, height: 95 },
          altText: {
            title: "Logo BPS",
            description: "Logo Badan Pusat Statistik",
            name: "logo-bps",
          },
        }),
      ],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 360, after: 220 },
      children: [run(title, { size: 36, bold: true, color: "0F172A" })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 180 },
      children: [run(subtitle, { size: 24, color: "334155" })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 520, after: 120 },
      children: [run("BPS Kabupaten Tegal", { size: 24, bold: true, color: "1D4ED8" })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 120 },
      children: [run(`Tanggal penyusunan: ${dateText}`, { size: 22, color: "475569" })],
    }),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

function tocPage() {
  return [
    p("Daftar Isi", {
      heading: HeadingLevel.HEADING_1,
      alignment: AlignmentType.LEFT,
      spacing: { before: 120, after: 220 },
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    new TableOfContents("", { hyperlink: true, headingStyleRange: "1-3" }),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

function buildUserGuidebook() {
  const dateText = formatTanggalIndonesia();
  const children = [];

  children.push(
    ...coverPage(
      "Guidebook Pengguna Aplikasi KABARE",
      "Panduan penggunaan aplikasi pemantauan dan analisis berita untuk mendukung pekerjaan statistik BPS Kabupaten Tegal",
      dateText,
    ),
    ...tocPage(),
  );

  children.push(
    p("1. Latar Belakang", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Aplikasi KABARE dibuat untuk menjawab kebutuhan kerja yang sangat nyata di lingkungan BPS Kabupaten Tegal. Dalam praktiknya, setelah kegiatan survei selesai dan hasil pengolahan mulai dibaca, pegawai sering mendapat tugas lanjutan ketika muncul angka yang terasa tidak biasa. Misalnya, pertumbuhan ekonomi bergerak di luar pola yang diharapkan, tingkat kemiskinan berubah cukup tajam, atau indikator pengangguran menunjukkan kondisi yang perlu dijelaskan lebih lanjut.",
    ),
    p(
      "Pada kondisi seperti itu, pegawai perlu menelusuri berita yang relevan untuk memahami konteks lapangan dan mencari kemungkinan penyebab perubahan angka. Proses ini biasanya memakan waktu karena berita tersebar di banyak sumber, istilah yang dipakai tidak selalu sama, dan pencarian manual sering membuat informasi penting terlewat.",
    ),
    p(
      "KABARE hadir untuk mempermudah proses tersebut. Aplikasi ini membantu pengguna mengumpulkan berita, membaca klasifikasi ekonomi yang sudah disiapkan sistem, menelusuri aktivitas ekonomi, melihat keterkaitan dengan PDRB pengeluaran, serta memanfaatkan AI untuk mempercepat analisis. Dengan begitu, pengguna tidak perlu memulai dari nol setiap kali harus menjelaskan fenomena di balik suatu indikator statistik.",
    ),

    p("2. Tujuan Aplikasi", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    ...bulletList([
      "Mempermudah pencarian berita yang berkaitan dengan perubahan indikator ekonomi, kemiskinan, dan pengangguran.",
      "Membantu pengguna menelusuri berita berdasarkan KBLI, aktivitas ekonomi, dan PDRB pengeluaran.",
      "Menyediakan ringkasan analisis berbasis AI agar pengguna lebih cepat memahami fenomena utama dalam suatu periode.",
      "Menyediakan chatbot AI yang dapat dipakai untuk tanya jawab cepat dengan konteks berita dan statistik resmi BPS.",
      "Merapikan alur kerja pencarian berita agar lebih konsisten, terdokumentasi, dan mudah diulang saat dibutuhkan.",
    ]),

    p("3. Gambaran Umum Fitur", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Saat masuk ke dashboard, pengguna akan menemukan beberapa area utama yang saling melengkapi. Masing-masing fitur dirancang untuk mendukung kebutuhan penelusuran berita dan pembacaan konteks statistik.",
    ),
    ...bulletList([
      "Data Berita, untuk melihat daftar berita yang sudah masuk ke sistem dan menelusurinya dengan filter yang lebih spesifik.",
      "Data Official Statistic, untuk melihat statistik resmi BPS yang relevan sebagai pembanding ketika membaca berita.",
      "Insight AI, untuk memperoleh ringkasan otomatis mengenai PDRB, kemiskinan, dan pengangguran pada periode tertentu.",
      "AI Chat, untuk melakukan tanya jawab berbasis berita dan statistik resmi secara lebih interaktif.",
      "Detail Berita, untuk membaca isi berita secara lebih lengkap dan melihat konteks klasifikasinya.",
    ]),

    p("4. Memulai Penggunaan", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Sebelum menggunakan fitur utama, pastikan Anda sudah memiliki akun dan kredensial yang diberikan oleh admin. Untuk pengguna baru, sistem dapat meminta pergantian password lebih dulu agar akun langsung aman digunakan.",
    ),
    p("Langkah awal yang disarankan:", {
      heading: HeadingLevel.HEADING_2,
      run: { size: 26, bold: true, color: "1E3A8A" },
    }),
    ...numberedList([
      "Buka halaman login aplikasi dan masukkan username serta password yang diberikan.",
      "Jika sistem meminta ganti password, selesaikan langkah tersebut terlebih dahulu.",
      "Setelah berhasil masuk, amati menu utama di sisi kiri untuk memahami bagian-bagian utama dashboard.",
      "Mulailah dari Data Berita jika tujuan Anda adalah mencari penyebab perubahan angka, atau langsung ke Insight AI jika Anda ingin ringkasan cepat per periode.",
    ], "num-1"),

    p("5. Menggunakan Menu Data Berita", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Menu Data Berita adalah area kerja utama ketika Anda ingin mencari berita yang paling relevan dengan suatu fenomena. Di sini, berita dapat dicari, disaring, diurutkan, dan ditinjau kembali berdasarkan kebutuhan analisis.",
    ),
    p("Yang bisa dilakukan di menu ini:", {
      heading: HeadingLevel.HEADING_2,
      run: { size: 26, bold: true, color: "1E3A8A" },
    }),
    ...bulletList([
      "Mencari berita berdasarkan kata kunci judul atau konteks tertentu.",
      "Menyaring berita berdasarkan KBLI.",
      "Menyaring berita berdasarkan aktivitas ekonomi.",
      "Menyaring berita berdasarkan PDRB pengeluaran.",
      "Menyaring berita berdasarkan status aktif, arsip, atau semua data.",
      "Mengurutkan berita agar pencarian lebih fokus, misalnya berdasarkan tanggal atau judul.",
      "Mengunduh data berita ke Excel bila diperlukan untuk olahan lanjutan.",
    ]),
    p(
      "Praktiknya, menu ini paling berguna saat Anda sudah punya dugaan awal. Misalnya, ketika ingin melihat apakah kenaikan pengangguran berkaitan dengan kondisi industri tertentu, Anda bisa mulai dari filter aktivitas ekonomi atau KBLI yang relevan, lalu membaca berita satu per satu dengan lebih terarah.",
    ),

    p("6. Membaca Detail Berita", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Saat menemukan berita yang terlihat penting, buka halaman detail berita. Halaman ini membantu Anda membaca isi berita dengan lebih utuh, bukan hanya dari judul atau potongan ringkasan. Langkah ini penting karena penyebab suatu fenomena sering baru terlihat jelas setelah isi berita dibaca dalam konteks lengkap.",
    ),
    ...bulletList([
      "Gunakan detail berita untuk memastikan apakah isi berita benar-benar berkaitan dengan indikator yang sedang Anda telaah.",
      "Perhatikan sumber berita, tanggal terbit, dan keterkaitan klasifikasi yang sudah menempel pada berita tersebut.",
      "Jika diperlukan, buka tautan berita asli untuk memastikan konteks media tetap terbaca dengan baik.",
    ]),

    p("7. Memahami Klasifikasi Berita", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Salah satu kekuatan KABARE adalah berita tidak hanya dikumpulkan, tetapi juga diklasifikasikan agar lebih mudah dicari kembali. Klasifikasi utama yang dipakai di aplikasi ini meliputi KBLI, aktivitas ekonomi, dan PDRB pengeluaran.",
    ),
    ...bulletList([
      "KBLI membantu menghubungkan berita dengan lapangan usaha yang relevan.",
      "Aktivitas ekonomi membantu melihat jenis kegiatan yang sedang terjadi, misalnya produksi, distribusi, perdagangan, atau layanan tertentu.",
      "PDRB pengeluaran membantu membaca berita dari sisi pengeluaran, seperti konsumsi, investasi, atau komponen lain yang berkaitan.",
    ]),
    p(
      "Klasifikasi ini tidak hanya berguna untuk pencarian cepat, tetapi juga membantu menjaga konsistensi analisis antarpegawai. Ketika berita sudah berada dalam kategori yang tepat, diskusi mengenai penyebab perubahan angka menjadi lebih mudah dilakukan.",
    ),

    p("8. Mengedit Klasifikasi Berita", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Walaupun sistem sudah menyiapkan klasifikasi otomatis, pengguna tetap bisa melakukan koreksi. Fitur ini penting karena dalam pekerjaan statistik, penilaian akhir tetap perlu mempertimbangkan pembacaan manusia, terutama ketika isi berita bersifat ambigu atau lintas sektor.",
    ),
    p("Saat mengedit klasifikasi, perhatikan hal berikut:", {
      heading: HeadingLevel.HEADING_2,
      run: { size: 26, bold: true, color: "1E3A8A" },
    }),
    ...numberedList([
      "Buka berita yang ingin diperbaiki klasifikasinya.",
      "Pilih KBLI yang paling sesuai dengan isi berita.",
      "Pilih aktivitas ekonomi yang paling menggambarkan kejadian utama dalam berita.",
      "Pilih kategori PDRB pengeluaran yang paling relevan.",
      "Simpan perubahan setelah seluruh pilihan sudah sesuai.",
    ], "num-2"),
    p(
      "Agar hasil klasifikasi tetap konsisten, hindari memilih kategori hanya dari judul. Selalu baca isi berita terlebih dahulu sebelum memutuskan perubahan.",
    ),

    p("9. Menggunakan Arsip Berita", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Fitur arsip berguna untuk merapikan daftar berita aktif. Tidak semua berita perlu selalu muncul pada tampilan utama. Dengan mengarsipkan berita yang sudah selesai ditelaah atau dinilai kurang relevan untuk kerja saat ini, tampilan data menjadi lebih fokus.",
    ),
    ...bulletList([
      "Gunakan status Aktif untuk berita yang masih ingin Anda pantau atau gunakan dalam analisis aktif.",
      "Gunakan status Arsip untuk berita yang ingin disimpan tetapi tidak perlu terus muncul di daftar utama.",
      "Gunakan filter Semua bila Anda ingin melihat keseluruhan data tanpa membedakan status.",
      "Berita yang sudah diarsipkan tetap bisa dipulihkan jika sewaktu-waktu diperlukan kembali.",
    ]),

    p("10. Menggunakan Data Official Statistic", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Selain berita, aplikasi juga menyediakan data official statistic BPS yang dapat dipakai sebagai pembanding. Fitur ini membantu Anda tetap menjaga analisis agar tidak hanya bergantung pada narasi media. Berita memberi konteks, sedangkan statistik resmi memberi pijakan angka.",
    ),
    ...bulletList([
      "Gunakan data ini untuk melihat PDRB ADHK dan PDRB ADHB menurut lapangan usaha.",
      "Gunakan data ini untuk melihat TPT dan TPAK saat menganalisis isu ketenagakerjaan.",
      "Gunakan data ini untuk melihat indikator kemiskinan saat menyandingkan berita dengan kondisi resmi yang tersedia.",
      "Jadikan data official statistic sebagai pembanding agar kesimpulan Anda tetap seimbang antara informasi berita dan statistik resmi.",
    ]),

    p("11. Menggunakan Insight AI", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Insight AI membantu pengguna memperoleh ringkasan cepat dari kumpulan berita yang tersedia dalam periode tertentu. Fitur ini sangat berguna saat Anda ingin memahami gambaran umum lebih dulu sebelum masuk ke pembacaan detail berita satu per satu.",
    ),
    p("Hal yang bisa Anda atur di fitur ini:", {
      heading: HeadingLevel.HEADING_2,
      run: { size: 26, bold: true, color: "1E3A8A" },
    }),
    ...bulletList([
      "Perspektif analisis, misalnya dari sudut pandang BPS, pemerintah, atau akademisi.",
      "Periode analisis, baik triwulanan, semesteran, maupun tahunan.",
      "Tahun analisis yang tersedia di sistem.",
      "Refresh insight bila Anda ingin memuat ulang hasil analisis yang lebih mutakhir.",
    ]),
    p("Cara memakainya secara efektif:", {
      heading: HeadingLevel.HEADING_2,
      run: { size: 26, bold: true, color: "1E3A8A" },
    }),
    ...numberedList([
      "Tentukan dulu periode dan tahun yang ingin Anda telaah.",
      "Pilih perspektif analisis sesuai kebutuhan. Jika fokus Anda adalah pembacaan yang dekat dengan statistik, gunakan perspektif BPS.",
      "Baca tiga kartu utama, yaitu PDRB, Kemiskinan, dan Pengangguran.",
      "Buka sumber berita yang tersedia pada masing-masing kategori jika Anda ingin menelusuri dasar narasi AI.",
      "Gunakan insight ini sebagai pintu masuk, bukan sebagai satu-satunya dasar kesimpulan.",
    ], "num-3"),

    p("12. Menggunakan AI Chat", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "AI Chat disiapkan untuk membantu tanya jawab yang lebih fleksibel. Jika Insight AI memberi ringkasan yang sifatnya lebih terstruktur, AI Chat membantu ketika Anda ingin menggali pertanyaan secara bertahap, membandingkan informasi, atau meminta penjelasan dengan bahasa yang lebih langsung.",
    ),
    p("Contoh pemanfaatan AI Chat:", {
      heading: HeadingLevel.HEADING_2,
      run: { size: 26, bold: true, color: "1E3A8A" },
    }),
    ...bulletList([
      "Menanyakan kemungkinan penyebab kenaikan atau penurunan indikator tertentu.",
      "Meminta rangkuman sektor ekonomi yang paling sering muncul dalam berita terbaru.",
      "Meminta kaitan antara berita tertentu dengan data resmi BPS.",
      "Menanyakan tren umum pada topik kemiskinan, pengangguran, atau PDRB.",
    ]),
    p("Tips bertanya agar hasil chat lebih membantu:", {
      heading: HeadingLevel.HEADING_2,
      run: { size: 26, bold: true, color: "1E3A8A" },
    }),
    ...numberedList([
      "Gunakan pertanyaan yang jelas dan fokus pada satu isu utama.",
      "Sebutkan periode atau sektor jika Anda sudah punya arah analisis.",
      "Periksa sitasi sumber yang ditampilkan bila jawaban perlu dipastikan kembali.",
      "Bersihkan percakapan jika Anda ingin memulai topik baru agar konteks tidak bercampur.",
    ], "num-4"),
    p(
      "Walaupun chatbot sangat membantu, pengguna tetap perlu menilai jawaban secara kritis. Gunakan AI Chat sebagai partner kerja untuk mempercepat telaah, bukan sebagai pengganti penilaian profesional.",
    ),

    p("13. Tips Penggunaan yang Disarankan", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    ...bulletList([
      "Mulailah dari Data Berita jika Anda butuh bukti lapangan yang spesifik.",
      "Gunakan Insight AI jika Anda ingin membaca gambaran umum lebih dulu sebelum mendalami satu per satu berita.",
      "Gunakan AI Chat ketika Anda membutuhkan penjelasan lanjutan, perbandingan, atau ringkasan cepat.",
      "Selalu padukan berita dengan data official statistic agar pembacaan tetap seimbang.",
      "Perbaiki klasifikasi jika Anda menemukan berita yang kurang tepat kategorinya. Langkah kecil ini akan sangat membantu kualitas data ke depan.",
      "Manfaatkan arsip untuk menjaga daftar kerja tetap rapi dan fokus.",
    ]),

    p("14. Penutup", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "KABARE dirancang untuk membantu pekerjaan yang sebelumnya banyak dilakukan secara manual, tersebar, dan memakan waktu. Dengan dukungan pencarian berita, klasifikasi ekonomi, arsip, statistik resmi, AI Insight, dan AI Chat, pengguna diharapkan bisa lebih cepat menemukan konteks yang dibutuhkan saat harus menjelaskan fenomena statistik di Kabupaten Tegal.",
    ),
    p(
      "Semakin konsisten aplikasi ini dipakai dan diperbarui dengan penilaian yang baik dari pengguna, semakin kuat pula manfaatnya sebagai alat bantu kerja internal BPS Kabupaten Tegal.",
    ),
  );

  return createDocument(children);
}

function buildAdminGuidebook() {
  const dateText = formatTanggalIndonesia();
  const children = [];

  children.push(
    ...coverPage(
      "Guidebook Admin Aplikasi KABARE",
      "Panduan pengelolaan akun dan operasional utama aplikasi pemantauan berita BPS Kabupaten Tegal",
      dateText,
    ),
    ...tocPage(),
  );

  children.push(
    p("1. Latar Belakang dan Peran Admin", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Admin memegang peran penting dalam menjaga agar aplikasi KABARE dapat digunakan dengan tertib, aman, dan berkelanjutan. Jika pengguna biasa berfokus pada pencarian berita dan analisis, maka admin bertanggung jawab memastikan akses pengguna berjalan dengan baik, akun terkelola dengan aman, dan operasional dasar aplikasi tetap lancar.",
    ),
    p(
      "Di lingkungan kerja BPS Kabupaten Tegal, peran ini penting karena aplikasi mendukung pekerjaan yang berkaitan langsung dengan pembacaan fenomena ekonomi, kemiskinan, dan pengangguran. Karena itu, pengelolaan admin perlu dilakukan dengan hati-hati, praktis, dan tetap tertib secara administrasi.",
    ),

    p("2. Tanggung Jawab Utama Admin", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    ...bulletList([
      "Membuat akun pengguna baru sesuai kebutuhan kerja.",
      "Mendistribusikan password sementara secara aman.",
      "Membantu pengguna yang lupa akses melalui pembuatan kode reset password.",
      "Menghapus akun yang sudah tidak digunakan atau tidak lagi berwenang.",
      "Memastikan hanya pihak yang tepat yang memiliki akses admin.",
      "Menjalankan scraping manual bila memang diperlukan oleh operasional.",
    ]),

    p("3. Akses Awal Admin", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Admin masuk ke aplikasi menggunakan akun yang memiliki role admin. Setelah login, admin dapat membuka dashboard utama dan halaman manajemen pengguna. Halaman khusus admin berada pada menu Manajemen User.",
    ),
    p("Alur akses yang disarankan:", {
      heading: HeadingLevel.HEADING_2,
      run: { size: 26, bold: true, color: "1E3A8A" },
    }),
    ...numberedList([
      "Login menggunakan akun admin.",
      "Pastikan identitas akun yang tampil di halaman sudah benar.",
      "Buka menu Manajemen User untuk melakukan pengelolaan akun.",
      "Kembali ke dashboard bila perlu memantau data berita, insight, atau kondisi scraping.",
    ], "num-5"),

    p("4. Membuat Akun Pengguna Baru", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Aplikasi menyediakan fitur pembuatan akun pengguna langsung dari halaman admin. Admin bahkan dapat menambahkan beberapa username sekaligus agar proses distribusi akun lebih efisien.",
    ),
    p("Langkah membuat akun baru:", {
      heading: HeadingLevel.HEADING_2,
      run: { size: 26, bold: true, color: "1E3A8A" },
    }),
    ...numberedList([
      "Masuk ke halaman Manajemen User.",
      "Isi username pengguna pada kolom yang tersedia. Jika membuat beberapa akun, pisahkan username sesuai format yang didukung sistem.",
      "Klik tombol Buat Pengguna.",
      "Sistem akan menampilkan password sementara. Informasi ini hanya muncul satu kali.",
      "Simpan dan kirimkan kredensial kepada pengguna melalui jalur yang aman.",
    ], "num-6"),
    p(
      "Perlu diingat bahwa pengguna baru akan diarahkan untuk mengganti password saat pertama kali login. Mekanisme ini penting untuk menjaga keamanan akses tanpa membebani admin membuat password permanen secara manual.",
    ),

    p("5. Membaca Daftar Pengguna", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Daftar pengguna membantu admin melihat kondisi akun yang ada di sistem. Informasi ini bukan hanya daftar nama, tetapi juga alat kontrol untuk melihat status akun dan kebutuhan tindak lanjut.",
    ),
    p("Kolom yang perlu diperhatikan:", {
      heading: HeadingLevel.HEADING_2,
      run: { size: 26, bold: true, color: "1E3A8A" },
    }),
    ...bulletList([
      "Username, untuk memastikan akun terdaftar atas nama yang benar.",
      "Role, untuk membedakan admin dan user biasa.",
      "Status password, untuk mengetahui apakah pengguna masih memakai password sementara atau sudah menggantinya.",
      "Kode reset, untuk melihat apakah ada kode autentikasi reset yang masih aktif.",
      "Aksi, untuk menjalankan pengelolaan lanjutan seperti membuat kode reset atau menghapus akun.",
    ]),

    p("6. Membuat Kode Reset Password", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Jika pengguna lupa password, admin tidak perlu membuat password baru secara manual. Sistem menyediakan kode autentikasi reset password yang dapat diberikan kepada pengguna. Cara ini lebih aman dan lebih rapi dari sisi administrasi akses.",
    ),
    p("Karakteristik kode reset:", {
      heading: HeadingLevel.HEADING_2,
      run: { size: 26, bold: true, color: "1E3A8A" },
    }),
    ...bulletList([
      "Kode dibuat khusus untuk satu pengguna.",
      "Kode berlaku selama 1 jam.",
      "Kode hanya dapat digunakan satu kali.",
      "Saat kode baru dibuat, kode lama tidak lagi dipakai.",
    ]),
    p("Langkah penggunaan:", {
      heading: HeadingLevel.HEADING_2,
      run: { size: 26, bold: true, color: "1E3A8A" },
    }),
    ...numberedList([
      "Cari nama pengguna pada tabel daftar user.",
      "Pilih aksi untuk membuat kode reset password.",
      "Catat kode dan masa berlakunya.",
      "Sampaikan kode kepada pengguna melalui jalur yang aman.",
      "Minta pengguna segera menyelesaikan reset password sebelum masa berlaku habis.",
    ], "num-1"),

    p("7. Menghapus Pengguna", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Penghapusan akun dilakukan ketika pengguna sudah tidak lagi memerlukan akses atau ketika akun harus ditutup karena alasan pengelolaan internal. Tindakan ini perlu dilakukan dengan hati-hati karena menyangkut kontrol akses aplikasi.",
    ),
    ...bulletList([
      "Pastikan akun yang akan dihapus memang tidak lagi diperlukan.",
      "Lakukan konfirmasi internal jika akun tersebut sebelumnya digunakan untuk pekerjaan aktif.",
      "Hindari penghapusan terburu-buru tanpa memastikan dampaknya pada pekerjaan tim.",
      "Sistem mencegah admin menghapus dirinya sendiri secara langsung.",
    ]),

    p("8. Operasional Scraping untuk Admin", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Dalam kondisi tertentu, admin dapat menjalankan scraping manual. Fitur ini berguna saat tim membutuhkan pembaruan data segera atau ketika ingin memastikan proses pengambilan berita berjalan kembali setelah ada kendala. Akses ini memang dibatasi untuk admin agar tidak digunakan sembarangan.",
    ),
    ...bulletList([
      "Gunakan scraping manual hanya jika ada kebutuhan operasional yang jelas.",
      "Pantau hasil scraping dan jumlah berita baru yang masuk setelah proses berjalan.",
      "Jika tidak ada kebutuhan mendesak, biarkan alur kerja sistem berjalan normal agar penggunaan tetap tertib.",
    ]),

    p("9. Praktik Keamanan yang Disarankan", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Karena admin mengelola akses seluruh pengguna, disiplin keamanan adalah hal yang tidak bisa ditawar. Tujuannya bukan untuk mempersulit pekerjaan, tetapi untuk menjaga agar aplikasi tetap dapat dipakai dengan aman dan dapat dipercaya.",
    ),
    ...bulletList([
      "Jangan mengirim password sementara atau kode reset melalui media yang terbuka dan mudah diteruskan tanpa kontrol.",
      "Segera minta pengguna mengganti password setelah menerima akses awal.",
      "Jangan membagikan akun admin kepada lebih dari satu orang.",
      "Lakukan pengecekan berkala pada daftar pengguna untuk memastikan tidak ada akun yang sudah tidak relevan tetapi masih aktif.",
      "Gunakan reset password dan pembuatan akun seperlunya, lalu catat kebutuhan administrasinya bila diperlukan di unit kerja.",
    ]),

    p("10. Dukungan Admin terhadap Pengguna", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Admin tidak hanya bertugas menjaga akses, tetapi juga membantu memastikan pengguna memahami alur kerja aplikasi. Bantuan sederhana dari admin sering sangat menentukan keberhasilan penggunaan aplikasi dalam pekerjaan sehari-hari.",
    ),
    ...bulletList([
      "Pastikan pengguna memahami bahwa berita dapat difilter berdasarkan KBLI, aktivitas ekonomi, dan PDRB pengeluaran.",
      "Arahkan pengguna untuk memanfaatkan Insight AI sebagai ringkasan awal, lalu menelusuri berita detail jika perlu.",
      "Ingatkan pengguna bahwa AI Chat bersifat membantu, sehingga hasilnya tetap perlu dibaca dengan kritis.",
      "Dorong pengguna untuk memperbaiki klasifikasi berita bila menemukan kategori yang kurang sesuai.",
    ]),

    p("11. Penutup", {
      heading: HeadingLevel.HEADING_1,
      run: { size: 30, bold: true, color: "0F172A" },
    }),
    p(
      "Peran admin dalam KABARE mungkin terlihat sederhana di permukaan, tetapi dampaknya besar bagi kelancaran penggunaan aplikasi oleh seluruh tim. Pengelolaan akun yang rapi, pengamanan akses yang disiplin, dan dukungan operasional yang tepat akan membuat aplikasi ini lebih stabil dan lebih bermanfaat untuk pekerjaan statistik di BPS Kabupaten Tegal.",
    ),
    p(
      "Dengan pengelolaan admin yang baik, pengguna dapat fokus pada inti pekerjaannya, yaitu memahami fenomena ekonomi dan sosial melalui kombinasi berita, klasifikasi, serta statistik resmi yang tersedia di aplikasi.",
    ),
  );

  return createDocument(children);
}

function createDocument(children) {
  return new Document({
    styles: {
      default: {
        document: {
          run: {
            font: "Arial",
            size: 24,
          },
        },
      },
      paragraphStyles: [
        {
          id: "Title",
          name: "Title",
          basedOn: "Normal",
          run: { size: 40, bold: true, color: "0F172A", font: "Arial" },
          paragraph: { alignment: AlignmentType.CENTER, spacing: { before: 200, after: 200 } },
        },
        {
          id: "Heading1",
          name: "Heading 1",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: { size: 30, bold: true, color: "0F172A", font: "Arial" },
          paragraph: { spacing: { before: 220, after: 160 }, outlineLevel: 0 },
        },
        {
          id: "Heading2",
          name: "Heading 2",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: { size: 26, bold: true, color: "1E3A8A", font: "Arial" },
          paragraph: { spacing: { before: 180, after: 120 }, outlineLevel: 1 },
        },
      ],
    },
    numbering,
    sections: [
      {
        properties: {
          page: {
            margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 },
          },
        },
        footers: {
          default: new Footer({
            children: [
              new Paragraph({
                alignment: AlignmentType.CENTER,
                children: [
                  run("Halaman ", { size: 20, color: "64748B" }),
                  new TextRun({ children: [PageNumber.CURRENT], size: 20, color: "64748B", font: "Arial" }),
                ],
              }),
            ],
          }),
        },
        children,
      },
    ],
  });
}

async function saveDoc(fileName, doc) {
  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(path.join(ROOT, fileName), buffer);
}

async function main() {
  await saveDoc("Guidebook Pengguna KABARE.docx", buildUserGuidebook());
  await saveDoc("Guidebook Admin KABARE.docx", buildAdminGuidebook());
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
