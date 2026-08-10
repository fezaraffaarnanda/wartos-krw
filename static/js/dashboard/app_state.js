
let filteredData = [];
let currentPage = 1;
const PER_PAGE = 15;
let sortField = "date_parsed";
let sortAsc = false;
let currentUser = null;
let _activeView = "overview";
let _overviewSummary = null;
let _filterOptions = { kbli_codes: [], aktivitas_codes: [], pdrb_pengeluaran_codes: [] };
let _sortKeyUi = "date";

const _tableFilterState = {
  search: "",
  date_from: "",
  date_to: "",
  kbli_code: "",
  aktivitas_code: "",
  pdrb_pengeluaran_code: "",
  archive_status: "relevant",
};

const _tablePaginationState = {
  page: 1,
  per_page: PER_PAGE,
  total_items: 0,
  total_pages: 1,
  has_prev: false,
  has_next: false,
};

const VIEW_META = {
  overview: {
    title: "WARTOS Dashboard",
    subtitle: "Pemantauan fenomena ekonomi berbasis berita lokal",
  },
  data: {
    title: "Data Berita",
    subtitle: "Tabel berita, filter, dan ekspor data",
  },
  "official-statistics": {
    title: "Data Official Statistic Terkini",
    subtitle: "Visualisasi statistik resmi BPS Kabupaten Karawang per tahun",
  },
  insight: {
    title: "Insight AI",
    subtitle: "Analisis otomatis indikator ekonomi, kemiskinan, dan pengangguran",
  },
  chat: {
    title: "AI Chat",
    subtitle: "Diskusi interaktif berbasis berita tersitasi",
  },
  scrape: {
    title: "Scraping Manual",
    subtitle: "Kontrol scraping manual untuk kebutuhan operasional admin",
  },
};

const BULAN_ID = {
  januari: 0,
  februari: 1,
  maret: 2,
  april: 3,
  mei: 4,
  juni: 5,
  juli: 6,
  agustus: 7,
  september: 8,
  oktober: 9,
  november: 10,
  desember: 11,
};

const SOURCE_KEYS = [
  "radartegal",
  "panturapost",
  "tribunjateng",
  "kompas",
  "setdategal",
];

const BULAN_NAMA_ID = [
  "Januari",
  "Februari",
  "Maret",
  "April",
  "Mei",
  "Juni",
  "Juli",
  "Agustus",
  "September",
  "Oktober",
  "November",
  "Desember",
];

let chartInstance = null;
let kbliChartInstance = null;
let clockTimer = null;
let pollTimer = null;
let refreshTimer = null;
let maxArticlesGlobal = 150;

const AUTO_REFRESH_MS = 5 * 60 * 1000;

let _selectedKbli = "";
let _selectedAktivitas = "";
let _selectedPdrbPengeluaran = "";
let _selectedArchiveStatus = "relevant";
let _filterDebounce = null;

let _kbliTooltipEl = null;
let _kbliTooltipArrow = null;

let _aiLoading = false;
let _currentYear = String(new Date().getFullYear());
let _aiInsightStream = null;
let _currentActor = "bps";
let _currentPeriod = "";

const _ACTOR_LABELS = {
  bps: "BPS",
  pemerintah: "Pemerintah (Bappeda)",
  akademisi: "Akademisi",
};

const _ACTOR_SUBTITLE_LABELS = {
  bps: "BPS",
  pemerintah: "Pemerintah (Bappeda/Bappenas)",
  akademisi: "Akademisi / Peneliti",
};

const _PERIOD_LABELS = {
  q1: "Triwulan I (Jan–Mar)",
  q2: "Triwulan II (Apr–Jun)",
  q3: "Triwulan III (Jul–Sep)",
  q4: "Triwulan IV (Okt–Des)",
  s1: "Semester I (Jan–Jun)",
  s2: "Semester II (Jul–Des)",
  yearly: "Tahunan (Jan–Des)",
};

let _chatLoading = false;
let _chatSessionId = "";
let _chatModalResolver = null;
let _chatReady = false;

let _officialStatsLoading = false;
let _officialStatsLoaded = false;
let _officialStatsYear = "2025";
let _officialStatsChartPdrbAdhk = null;
let _officialStatsChartPdrbAdhb = null;
let _officialStatsChartTptTpak = null;
let _officialStatsChartKemiskinan = null;
let _officialStatsChartPdrbPengeluaranAdhk = null;
let _officialStatsChartPdrbPengeluaranAdhb = null;

let _articleEditorState = {
  beritaId: null,
  title: "",
  source: "",
  kbliCode: "",
  aktivitasCode: "",
  pdrbPengeluaranCode: "",
  isArchived: false,
};
