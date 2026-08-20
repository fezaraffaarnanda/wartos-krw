"""Service statistik resmi BPS untuk dashboard dan konteks AI."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import html
import re
import time
from threading import Lock
from typing import Any

from clients.bps import BPSWebApiClient
from clients.google_sheets import GoogleSheetsClient
from config.region import FOCUS_AREA_LABEL
from repositories.official_statistics import (
    load_official_statistics_year_snapshots,
    upsert_official_statistics_snapshots,
)

_PAGE_SUPPORTED_YEARS = (2026, 2025, 2024)
_DEFAULT_PAGE_YEAR = _PAGE_SUPPORTED_YEARS[0]
_CACHE_TTL_SECONDS = 30 * 60
_PDRB_TOP_LIMIT = 8
_AI_TOPIC_DEFAULTS = ("pdrb", "kemiskinan", "pengangguran")

# `turtahun` pada endpoint list/model/data untuk var PDRB triwulanan.
_PERIOD_KEY_BY_TURTAHUN_ID = {
    "31": "q1",
    "32": "q2",
    "33": "q3",
    "34": "q4",
    "35": "annual",
}
_PERIOD_LABELS = {
    "q1": "Triwulan I",
    "q2": "Triwulan II",
    "q3": "Triwulan III",
    "q4": "Triwulan IV",
    "annual": "Tahunan",
}
_PERIOD_ORDER = ("q1", "q2", "q3", "q4", "annual")
# Penanda sementara untuk `turtahun` yang tidak memetakan ke triwulan mana pun.
_UNLABELED_PERIOD_KEY = "__unlabeled__"

# Kode kategori BPS untuk 17 lapangan usaha, terurut mengikuti `vervar.val` 1..17.
# Tidak bisa diturunkan dari chr(64 + val): BPS menggabung M,N dan R,S,T,U.
_LAPANGAN_USAHA_CODES = (
    "A", "B", "C", "D", "E", "F", "G", "H", "I",
    "J", "K", "L", "M,N", "O", "P", "Q", "R,S,T,U",
)

_PDRB_TOTAL_LABEL = "Produk Domestik Regional Bruto"

_YEAR_CACHE_LOCK = Lock()
_YEAR_CACHE: dict[int, dict[str, Any]] = {}


@dataclass(frozen=True)
class DatasetDefinition:
    key: str
    title: str
    subtitle: str
    period_key: str
    # (nama payload, nama method di BPSWebApiClient). Satu dataset tampilan bisa
    # dirakit dari beberapa var BPS sekaligus.
    sources: tuple[tuple[str, str], ...]
    normalizer_method: str
    # Client sumber data; lihat `OfficialStatisticsService._clients`.
    client: str = "bps"
    # Hanya untuk dataset PDRB triwulanan: apakah baris diberi kode kategori.
    use_category_codes: bool = False


_DATASET_DEFINITIONS: tuple[DatasetDefinition, ...] = (
    DatasetDefinition(
        key="pdrb_lapangan_usaha",
        title="PDRB Lapangan Usaha",
        subtitle="17 kategori, ADHB dan ADHK 2010=100",
        period_key="quarterly",
        sources=(
            ("adhb", "fetch_pdrb_lu_adhb"),
            ("adhk", "fetch_pdrb_lu_adhk"),
            ("distribusi", "fetch_pdrb_lu_distribusi"),
        ),
        normalizer_method="_normalize_pdrb_triwulanan",
        use_category_codes=True,
    ),
    DatasetDefinition(
        key="pdrb_pengeluaran",
        title="PDRB Pengeluaran",
        subtitle="6 komponen, ADHB dan ADHK 2010=100",
        period_key="quarterly",
        sources=(
            ("adhb", "fetch_pdrb_pengeluaran_adhb"),
            ("adhk", "fetch_pdrb_pengeluaran_adhk"),
            ("distribusi", "fetch_pdrb_pengeluaran_distribusi"),
        ),
        normalizer_method="_normalize_pdrb_triwulanan",
    ),
    DatasetDefinition(
        key="tpt_tpak",
        title="TPT dan TPAK",
        subtitle="Seri tahunan Kabupaten Karawang",
        period_key="annual",
        sources=(("tpak", "fetch_tpak_series"), ("tpt", "fetch_tpt_series")),
        normalizer_method="_normalize_ketenagakerjaan",
    ),
    DatasetDefinition(
        key="kemiskinan",
        title="Kemiskinan",
        subtitle="Seri tahunan Kabupaten Karawang",
        period_key="annual",
        sources=(("sheet", "fetch_kemiskinan"),),
        normalizer_method="_normalize_kemiskinan_series",
        client="sheets",
    ),
)


# Label indikator ketenagakerjaan ditulis manual: label `var` dari BPS memuat nama
# wilayah dan rentang tahun ("... Kabupaten Karawang 2013-2025") yang tidak cocok
# dipakai sebagai judul kolom.
_LABOR_INDICATOR_LABELS = {
    "tpak": "TPAK (Tingkat Partisipasi Angkatan Kerja)",
    "tpt": "TPT (Tingkat Pengangguran Terbuka)",
}


# Metrik kemiskinan seperti tertulis di sheet sumber. `row_label` dicocokkan ke
# kolom pertama (huruf besar, dibawa turun kalau selnya kosong) dan `row_unit` ke
# kolom kedua — P0 punya dua baris yang hanya dibedakan satuannya.
_KEMISKINAN_METRICS: tuple[dict[str, Any], ...] = (
    {"key": "poverty_rate", "row_label": "P0", "row_unit": "persen", "delta_suffix": " poin",
     "label": "Persentase Penduduk Miskin (P0)", "unit": "Persen", "format": "decimal"},
    {"key": "poor_population", "row_label": "P0", "row_unit": "ribuan jiwa", "delta_suffix": " ribu jiwa",
     "label": "Jumlah Penduduk Miskin", "unit": "Ribu jiwa", "format": "decimal"},
    {"key": "depth_index", "row_label": "P1", "row_unit": "", "delta_suffix": " poin",
     "label": "Indeks Kedalaman Kemiskinan (P1)", "unit": "Indeks", "format": "decimal"},
    {"key": "severity_index", "row_label": "P2", "row_unit": "", "delta_suffix": " poin",
     "label": "Indeks Keparahan Kemiskinan (P2)", "unit": "Indeks", "format": "decimal"},
    {"key": "poverty_line", "row_label": "GK", "row_unit": "", "delta_suffix": " rupiah",
     "label": "Garis Kemiskinan", "unit": "Rp/kapita/bulan", "format": "integer"},
    {"key": "gini_ratio", "row_label": "GINI RATIO", "row_unit": "", "delta_suffix": " poin",
     "label": "Gini Ratio", "unit": "Rasio", "format": "decimal3"},
)


# Dinaikkan setiap kali bentuk keluaran normalizer berubah, supaya snapshot
# lama di DB tidak dipakai ulang oleh frontend yang sudah mengharap bentuk baru.
_SNAPSHOT_SCHEMA_VERSION = 3

_ACTIVE_DATASET_KEYS = frozenset(definition.key for definition in _DATASET_DEFINITIONS)


class OfficialStatisticsService:
    """Orkestrasi fetch, normalisasi, cache, dan persistence statistik resmi BPS."""

    def __init__(
        self,
        bps_client: BPSWebApiClient | None = None,
        sheets_client: GoogleSheetsClient | None = None,
    ):
        self._clients = {
            "bps": bps_client or BPSWebApiClient(),
            "sheets": sheets_client or GoogleSheetsClient(),
        }

    def get_dashboard_payload(self, year: int | None = None, force_refresh: bool = False) -> dict[str, Any]:
        selected_year = self._normalize_page_year(year)
        datasets = self.fetch_statistics_bundle(selected_year, force_refresh=force_refresh)
        dataset_count = len(datasets)
        available_count = sum(1 for dataset in datasets.values() if dataset.get("available"))

        return {
            "status": "ok",
            "year": selected_year,
            "supported_years": list(_PAGE_SUPPORTED_YEARS),
            "dataset_count": dataset_count,
            "available_count": available_count,
            "datasets": datasets,
            "generated_at": int(time.time()),
        }

    def fetch_statistics_bundle(self, year: int, force_refresh: bool = False) -> dict[str, Any]:
        current_year = int(year)
        current_bundle = self._load_bundle_without_comparison(current_year, force_refresh=force_refresh)
        previous_bundle = self._load_previous_year_bundle(current_year)
        return self._attach_bundle_comparisons(current_bundle, previous_bundle)

    def build_ai_context(self, requested_year: int | None = None, topics: set[str] | None = None) -> dict[str, Any]:
        topic_set = self._normalize_topics(topics)
        candidate_years = self._build_ai_candidate_years(requested_year)

        for year in candidate_years:
            datasets = self.fetch_statistics_bundle(year, force_refresh=False)
            topic_blocks = self._build_ai_topic_blocks(datasets, year, topic_set)
            if any(topic_blocks.values()):
                return {
                    "requested_year": requested_year,
                    "actual_year": year,
                    "topics": topic_blocks,
                    "has_data": True,
                }

        return {
            "requested_year": requested_year,
            "actual_year": None,
            "topics": {topic: "" for topic in topic_set},
            "has_data": False,
        }

    @staticmethod
    def detect_chat_topics(query: str) -> set[str]:
        text = str(query or "").lower()
        topics: set[str] = set()

        if any(
            keyword in text
            for keyword in (
                "pdrb",
                "adhk",
                "adhb",
                "lapangan usaha",
                "pertumbuhan ekonomi",
                "sektor",
                "pengeluaran",
                "konsumsi rumah tangga",
                "konsumsi pemerintah",
                "pmtb",
                "inventori",
                "ekspor",
                "impor",
                "triwulan",
                "tw i",
                "distribusi pdrb",
                "harga implisit",
                "deflator",
                "struktur ekonomi",
            )
        ):
            topics.add("pdrb")

        if any(keyword in text for keyword in ("kemiskinan", "miskin", "garis kemiskinan", "bansos", "kesejahteraan")):
            topics.add("kemiskinan")

        if any(keyword in text for keyword in ("pengangguran", "tpt", "tpak", "angkatan kerja", "tenaga kerja", "phk", "lowongan kerja")):
            topics.add("pengangguran")

        if topics:
            return topics

        if any(keyword in text for keyword in ("statistik resmi", "data resmi", "bps", "ekonomi karawang")):
            return set(_AI_TOPIC_DEFAULTS)

        return set()

    @staticmethod
    def detect_requested_year(text: str) -> int | None:
        match = re.search(r"\b(20\d{2})\b", str(text or ""))
        return int(match.group(1)) if match else None

    def _build_ai_candidate_years(self, requested_year: int | None) -> list[int]:
        candidates: list[int] = []
        if requested_year is not None:
            candidates.append(int(requested_year))
        candidates.extend(_PAGE_SUPPORTED_YEARS)

        unique_candidates: list[int] = []
        seen: set[int] = set()
        for year in candidates:
            if year in seen:
                continue
            unique_candidates.append(year)
            seen.add(year)
        return unique_candidates

    def _load_bundle_without_comparison(self, year: int, force_refresh: bool = False) -> dict[str, Any]:
        normalized_year = int(year)

        if not force_refresh:
            cached = self._read_cache(normalized_year)
            if cached is not None:
                return deepcopy(cached)

            # Snapshot dataset yang sudah dipensiunkan bisa tertinggal di DB, dan
            # snapshot lama bisa memakai bentuk normalisasi yang sudah berubah.
            # Bundle hanya boleh berisi dataset yang masih terdaftar dan sebentuk
            # dengan normalizer saat ini; sisanya diambil ulang dari Web API.
            persisted = {
                key: dataset
                for key, dataset in load_official_statistics_year_snapshots(normalized_year).items()
                if key in _ACTIVE_DATASET_KEYS
                and dataset.get("schema_version") == _SNAPSHOT_SCHEMA_VERSION
            }
            if self._is_complete_bundle(persisted):
                self._write_cache(normalized_year, persisted)
                return deepcopy(persisted)

        datasets, snapshots = self._fetch_remote_bundle(normalized_year)
        if snapshots:
            upsert_official_statistics_snapshots(snapshots)
        self._write_cache(normalized_year, datasets)
        return deepcopy(datasets)

    def _load_previous_year_bundle(self, year: int) -> dict[str, Any]:
        previous_year = int(year) - 1
        if previous_year < 2000:
            return {}

        try:
            return self._load_bundle_without_comparison(previous_year, force_refresh=False)
        except Exception as exc:
            print(f"[BPS] Gagal memuat pembanding tahun {previous_year}: {exc}")
            return {}

    def _fetch_remote_bundle(self, year: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        datasets: dict[str, Any] = {}
        snapshots: list[dict[str, Any]] = []

        for definition in _DATASET_DEFINITIONS:
            raw_payloads = self._safe_fetch_raw_payloads(definition, year)
            normalized_dataset = self._safe_normalize_dataset(definition, raw_payloads, year)
            datasets[definition.key] = normalized_dataset
            snapshots.append(self._build_snapshot_row(definition, year, raw_payloads, normalized_dataset))

        return datasets, snapshots

    def _safe_fetch_raw_payloads(self, definition: DatasetDefinition, year: int) -> dict[str, dict[str, Any]]:
        payloads: dict[str, dict[str, Any]] = {}

        for source_name, fetch_method in definition.sources:
            try:
                fetcher = getattr(self._clients[definition.client], fetch_method)
                payloads[source_name] = fetcher(year)
            except Exception as exc:
                print(f"[BPS] Gagal fetch {definition.key}/{source_name} tahun {year}: {exc}")
                payloads[source_name] = {"status": "ERROR", "message": str(exc)}

        return payloads

    def _safe_normalize_dataset(
        self,
        definition: DatasetDefinition,
        raw_payloads: dict[str, dict[str, Any]],
        year: int,
    ) -> dict[str, Any]:
        try:
            normalizer = getattr(self, definition.normalizer_method)
            return normalizer(definition, raw_payloads, year)
        except Exception as exc:
            print(f"[BPS] Gagal normalisasi {definition.key} tahun {year}: {exc}")
            return self._build_unavailable_dataset(definition, year, str(exc))

    def _build_snapshot_row(
        self,
        definition: DatasetDefinition,
        year: int,
        raw_payloads: dict[str, dict[str, Any]],
        normalized_dataset: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "dataset_key": definition.key,
            "year": int(year),
            "period_key": definition.period_key,
            "title": definition.title,
            "source": normalized_dataset.get("source"),
            "updated_at_source_text": normalized_dataset.get("updated_at"),
            "raw_payload": raw_payloads,
            "normalized_payload": {
                **normalized_dataset,
                "schema_version": _SNAPSHOT_SCHEMA_VERSION,
            },
            "fetched_at": self._now_iso(),
        }

    def _attach_bundle_comparisons(
        self,
        current_bundle: dict[str, Any],
        previous_bundle: dict[str, Any],
    ) -> dict[str, Any]:
        compared_bundle = deepcopy(current_bundle)
        for key, current_dataset in compared_bundle.items():
            previous_dataset = previous_bundle.get(key) if previous_bundle else None
            current_dataset["comparison"] = self._build_dataset_comparison(current_dataset, previous_dataset)
        return compared_bundle

    def _build_dataset_comparison(
        self,
        current_dataset: dict[str, Any],
        previous_dataset: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not current_dataset.get("available") or not previous_dataset or not previous_dataset.get("available"):
            return {}

        dataset_key = str(current_dataset.get("key") or "")
        if dataset_key.startswith("pdrb_"):
            return self._build_pdrb_triwulanan_comparison(current_dataset, previous_dataset)
        return {}

    def _build_pdrb_triwulanan_comparison(
        self,
        current_dataset: dict[str, Any],
        previous_dataset: dict[str, Any],
    ) -> dict[str, Any]:
        """Bandingkan total PDRB ADHB: YoY per triwulan yang sama, plus QoQ dalam tahun berjalan.

        Kalau tahun pembanding tidak punya triwulan yang sama, entri YoY-nya kosong
        dan UI menyembunyikan delta — lebih baik hilang daripada mengarang pertumbuhan.
        """
        current_periods = current_dataset.get("by_period") or {}
        previous_periods = previous_dataset.get("by_period") or {}
        filled_keys = [key for key in _PERIOD_ORDER if key in current_periods]

        year_over_year: dict[str, Any] = {}
        for period_key in filled_keys:
            comparison = self._build_value_comparison(
                ((current_periods.get(period_key) or {}).get("total") or {}).get("adhb"),
                ((previous_periods.get(period_key) or {}).get("total") or {}).get("adhb"),
                unit_suffix=" miliar",
            )
            if comparison:
                year_over_year[period_key] = comparison

        quarter_keys = [key for key in filled_keys if key != "annual"]
        quarter_over_quarter: dict[str, Any] = {}
        for previous_key, period_key in zip(quarter_keys, quarter_keys[1:]):
            comparison = self._build_value_comparison(
                ((current_periods.get(period_key) or {}).get("total") or {}).get("adhb"),
                ((current_periods.get(previous_key) or {}).get("total") or {}).get("adhb"),
                unit_suffix=" miliar",
            )
            if comparison:
                comparison["previous_period_label"] = _PERIOD_LABELS[previous_key]
                quarter_over_quarter[period_key] = comparison

        if not year_over_year and not quarter_over_quarter:
            return {}

        return {
            "previous_year": previous_dataset.get("year"),
            "year_over_year": year_over_year,
            "quarter_over_quarter": quarter_over_quarter,
        }

    def _build_ai_topic_blocks(
        self,
        datasets: dict[str, Any],
        year: int,
        topics: set[str],
    ) -> dict[str, str]:
        blocks = {topic: "" for topic in topics}

        if "pdrb" in topics:
            blocks["pdrb"] = self._build_pdrb_ai_block(datasets, year)
        if "pengangguran" in topics:
            blocks["pengangguran"] = self._build_tpt_ai_block(datasets, year)
        if "kemiskinan" in topics:
            blocks["kemiskinan"] = self._build_kemiskinan_ai_block(datasets, year)

        return blocks

    def _build_pdrb_ai_block(self, datasets: dict[str, Any], year: int) -> str:
        lapangan_usaha = datasets.get("pdrb_lapangan_usaha") or {}
        pengeluaran = datasets.get("pdrb_pengeluaran") or {}

        if not any(dataset.get("available") for dataset in (lapangan_usaha, pengeluaran)):
            return ""

        period_key = lapangan_usaha.get("default_period_key") or pengeluaran.get("default_period_key") or ""
        period_label = _PERIOD_LABELS.get(period_key, "")
        period_text = f"{period_label} {year}".strip()

        lines = [f"Statistik resmi BPS untuk PDRB {FOCUS_AREA_LABEL}, periode {period_text}:"]

        if lapangan_usaha.get("available"):
            lines.extend(self._build_pdrb_ai_lines(lapangan_usaha, period_key, "lapangan usaha", top_limit=5))
        if pengeluaran.get("available"):
            lines.extend(self._build_pdrb_ai_lines(pengeluaran, period_key, "komponen pengeluaran", top_limit=0))

        lines.append(self._build_pdrb_ai_coverage_note(lapangan_usaha, pengeluaran, year))
        lines.append(
            "Gunakan statistik resmi ini sebagai baseline. Jika pengguna menanyakan penyebab perubahan, kaitkan angka resmi dengan berita relevan dan jelaskan apakah dukungan berita cukup atau masih indikatif."
        )
        return "\n".join(line for line in lines if line)

    def _build_pdrb_ai_lines(
        self,
        dataset: dict[str, Any],
        period_key: str,
        lens_label: str,
        *,
        top_limit: int,
    ) -> list[str]:
        block = (dataset.get("by_period") or {}).get(period_key) or {}
        rows = block.get("rows") or []
        if not rows:
            return []

        total = block.get("total") or {}
        lines = [
            f"- Menurut {lens_label}: PDRB ADHB {total.get('adhb_display', '—')} miliar rupiah, "
            f"ADHK 2010 {total.get('adhk_display', '—')} miliar rupiah, "
            f"indeks harga implisit {total.get('implicit_index_display', '—')}."
        ]

        listed_rows = rows[:top_limit] if top_limit else rows
        detail = "; ".join(
            f"{row['label']} {row['adhb_display']} miliar ({row['share_display']}%)"
            for row in listed_rows
        )
        prefix = f"{top_limit} terbesar" if top_limit else "Rincian"
        lines.append(f"  {prefix}: {detail}.")

        comparison = dataset.get("comparison") or {}
        year_over_year = (comparison.get("year_over_year") or {}).get(period_key) or {}
        if year_over_year.get("delta_percentage_display"):
            lines.append(
                f"  Dibanding periode sama {comparison.get('previous_year')}, total ADHB berubah "
                f"{year_over_year.get('delta_display')} ({year_over_year.get('delta_percentage_display')})."
            )

        quarter_over_quarter = (comparison.get("quarter_over_quarter") or {}).get(period_key) or {}
        if quarter_over_quarter.get("delta_percentage_display"):
            lines.append(
                f"  Dibanding {quarter_over_quarter.get('previous_period_label')}, total ADHB berubah "
                f"{quarter_over_quarter.get('delta_display')} ({quarter_over_quarter.get('delta_percentage_display')})."
            )

        return lines

    @staticmethod
    def _build_pdrb_ai_coverage_note(
        lapangan_usaha: dict[str, Any],
        pengeluaran: dict[str, Any],
        year: int,
    ) -> str:
        """Cegah LLM mengarang laju pertumbuhan saat hanya satu periode yang rilis."""
        filled_periods = {
            period["period_key"]
            for dataset in (lapangan_usaha, pengeluaran)
            for period in (dataset.get("periods") or [])
            if period.get("available")
        }
        has_comparison = any(
            (dataset.get("comparison") or {}).get("year_over_year")
            or (dataset.get("comparison") or {}).get("quarter_over_quarter")
            for dataset in (lapangan_usaha, pengeluaran)
        )
        if len(filled_periods) > 1 or has_comparison:
            return ""

        labels = ", ".join(_PERIOD_LABELS[key] for key in _PERIOD_ORDER if key in filled_periods)
        return (
            f"- Catatan cakupan: BPS baru merilis {labels} {year} untuk tabel ini, dan tidak ada "
            "periode pembanding. Jangan menyebut angka pertumbuhan PDRB — sampaikan bahwa laju "
            "pertumbuhan resmi belum bisa dihitung dari data yang tersedia."
        )

    def _build_tpt_ai_block(self, datasets: dict[str, Any], year: int) -> str:
        dataset = datasets.get("tpt_tpak") or {}
        if not dataset.get("available"):
            return ""

        indicators = dataset.get("indicators") or {}
        latest_year = dataset.get("latest_year")
        lines = [
            f"Statistik resmi BPS untuk ketenagakerjaan {FOCUS_AREA_LABEL}, "
            f"data terakhir tahun {latest_year}:"
        ]

        for indicator_key in ("tpak", "tpt"):
            indicator = indicators.get(indicator_key) or {}
            if indicator.get("total") is None:
                continue
            line = f"- {indicator.get('label')} {latest_year}: {indicator.get('total_display')} persen."
            change = indicator.get("change") or {}
            if change.get("delta_display"):
                line += (
                    f" Dibanding {change.get('previous_year')} ({change.get('previous_total_display')} persen), "
                    f"berubah {change.get('delta_display')} ({change.get('delta_percentage_display', '—')})."
                )
            lines.append(line)
            lowest = indicator.get("lowest") or {}
            highest = indicator.get("highest") or {}
            if lowest.get("year") and highest.get("year"):
                lines.append(
                    f"  Rentang seri: terendah {lowest.get('value_display')} persen ({lowest.get('year')}), "
                    f"tertinggi {highest.get('value_display')} persen ({highest.get('year')})."
                )

        series_text = self._build_labor_series_text(dataset.get("series") or [])
        if series_text:
            lines.append(f"- Seri tahunan (tahun: TPAK / TPT): {series_text}.")

        if dataset.get("is_latest_fallback"):
            lines.append(
                f"- Catatan cakupan: BPS belum merilis angka {year}; angka terbaru yang resmi "
                f"adalah tahun {latest_year}. Jangan menyebut angka TPT atau TPAK {year}."
            )

        lines.append(
            "Gunakan angka resmi ini sebagai baseline. Saat menjelaskan penyebab perubahan, kaitkan dengan berita tentang rekrutmen, PHK, pelatihan kerja, atau pergeseran sektor kerja."
        )
        return "\n".join(lines)

    @staticmethod
    def _build_labor_series_text(series: list[dict[str, Any]]) -> str:
        parts = [
            f"{point.get('year')}: {point.get('tpak_display', '—')} / {point.get('tpt_display', '—')}"
            for point in series
            if point.get("tpak") is not None or point.get("tpt") is not None
        ]
        return "; ".join(parts)

    def _build_kemiskinan_ai_block(self, datasets: dict[str, Any], year: int) -> str:
        dataset = datasets.get("kemiskinan") or {}
        if not dataset.get("available"):
            return ""

        metrics = dataset.get("metrics") or {}
        latest_year = dataset.get("latest_year")
        lines = [
            f"Statistik kemiskinan {FOCUS_AREA_LABEL}, data terakhir tahun {latest_year}:"
        ]

        for metric_key in (
            "poverty_rate",
            "poor_population",
            "poverty_line",
            "depth_index",
            "severity_index",
            "gini_ratio",
        ):
            metric = metrics.get(metric_key) or {}
            if metric.get("value") is None:
                continue
            line = (
                f"- {metric.get('label')} {metric.get('latest_year')}: "
                f"{metric.get('value_display')} {metric.get('unit')}."
            )
            change = metric.get("change") or {}
            if change.get("delta_display"):
                line += (
                    f" Dibanding {change.get('previous_year')} "
                    f"({change.get('previous_value_display')}), berubah "
                    f"{change.get('delta_display')} ({change.get('delta_percentage_display', '\u2014')})."
                )
            lines.append(line)

        poverty_rate = metrics.get("poverty_rate") or {}
        lowest = poverty_rate.get("lowest") or {}
        highest = poverty_rate.get("highest") or {}
        if lowest.get("year") and highest.get("year"):
            lines.append(
                f"- Rentang seri persentase penduduk miskin: terendah {lowest.get('value_display')} persen "
                f"({lowest.get('year')}), tertinggi {highest.get('value_display')} persen ({highest.get('year')})."
            )

        series_text = self._build_kemiskinan_series_text(dataset.get("series") or [])
        if series_text:
            lines.append(
                f"- Seri tahunan (tahun: P0 persen / jumlah ribu jiwa): {series_text}."
            )

        if dataset.get("is_latest_fallback"):
            lines.append(
                f"- Catatan cakupan: angka {year} belum tersedia; rilis terakhir adalah tahun "
                f"{latest_year}. Jangan menyebut angka kemiskinan {year}."
            )

        lines.append(
            "Gunakan angka resmi ini sebagai acuan utama. Jika menjelaskan penyebab, kaitkan dengan berita tentang daya beli, pangan, bansos, pekerjaan, atau tekanan biaya hidup."
        )
        return "\n".join(lines)

    @staticmethod
    def _build_kemiskinan_series_text(series: list[dict[str, Any]]) -> str:
        parts = [
            f"{point.get('year')}: {point.get('poverty_rate_display', '\u2014')} / "
            f"{point.get('poor_population_display', '\u2014')}"
            for point in series
            if point.get("poverty_rate") is not None or point.get("poor_population") is not None
        ]
        return "; ".join(parts)

    def _normalize_ketenagakerjaan(
        self,
        definition: DatasetDefinition,
        payloads: dict[str, dict[str, Any]],
        year: int,
    ) -> dict[str, Any]:
        """Rakit seri tahunan TPAK (var 571) dan TPT (var 570) jadi satu dataset.

        Kedua var hanya punya satu nilai per tahun untuk Kabupaten Karawang, jadi
        nilai tunggal tahun terpilih terlalu miskin untuk dijadikan kartu. Yang
        dipakai adalah serinya, dipotong sampai tahun terpilih supaya selektor
        tahun tetap berarti.
        """
        series_by_indicator: dict[str, dict[int, float]] = {}
        sources: list[str] = []
        updates: list[str] = []

        for indicator_key in _LABOR_INDICATOR_LABELS:
            payload = payloads.get(indicator_key) or {}
            values, source_note, last_update = self._parse_annual_series(payload, year)
            series_by_indicator[indicator_key] = values
            if source_note:
                sources.append(source_note)
            if last_update:
                updates.append(last_update)

        covered_years = sorted(
            {point_year for values in series_by_indicator.values() for point_year in values}
        )
        if not covered_years:
            return self._build_unavailable_dataset(
                definition, year, "Tidak ada data TPT/TPAK untuk tahun ini."
            )

        series = [
            {
                "year": point_year,
                "year_label": str(point_year),
                **{
                    field: value
                    for indicator_key, values in series_by_indicator.items()
                    for field, value in (
                        (indicator_key, values.get(point_year)),
                        (
                            f"{indicator_key}_display",
                            self._format_decimal(values.get(point_year)),
                        ),
                    )
                },
            }
            for point_year in covered_years
        ]

        latest_year = covered_years[-1]
        indicators = {
            indicator_key: self._build_labor_indicator(indicator_key, values, covered_years)
            for indicator_key, values in series_by_indicator.items()
        }

        return {
            "key": definition.key,
            "title": definition.title,
            "subtitle": definition.subtitle,
            "available": True,
            "year": year,
            "unit": "Persen",
            "updated_at": max(updates) if updates else "",
            "source": sources[0] if sources else "Web API BPS",
            "series": series,
            "indicators": indicators,
            "latest_year": latest_year,
            # BPS merilis data tahunan ini terlambat, jadi tahun terpilih sering
            # belum terisi. Kartu tetap menampilkan tahun terakhir yang ada, tapi
            # menandainya supaya tidak terbaca sebagai angka tahun berjalan.
            "is_latest_fallback": latest_year != int(year),
        }

    def _build_labor_indicator(
        self,
        indicator_key: str,
        values: dict[int, float],
        covered_years: list[int],
    ) -> dict[str, Any]:
        filled_years = [point_year for point_year in covered_years if values.get(point_year) is not None]
        if not filled_years:
            return {
                "key": indicator_key,
                "label": _LABOR_INDICATOR_LABELS[indicator_key],
                "latest_year": None,
                "total": None,
                "total_display": "—",
                "change": {},
                "lowest": {},
                "highest": {},
            }

        latest_year = filled_years[-1]
        latest_value = values[latest_year]
        change = (
            self._build_value_comparison(
                latest_value, values[filled_years[-2]], unit_suffix=" poin"
            )
            if len(filled_years) > 1
            else {}
        )
        if change:
            change["previous_year"] = filled_years[-2]
            change["previous_total_display"] = self._format_decimal(values[filled_years[-2]])

        lowest_year = min(filled_years, key=lambda point_year: values[point_year])
        highest_year = max(filled_years, key=lambda point_year: values[point_year])

        return {
            "key": indicator_key,
            "label": _LABOR_INDICATOR_LABELS[indicator_key],
            "latest_year": latest_year,
            "total": latest_value,
            "total_display": self._format_decimal(latest_value),
            "change": change,
            "lowest": {
                "year": lowest_year,
                "value": values[lowest_year],
                "value_display": self._format_decimal(values[lowest_year]),
            },
            "highest": {
                "year": highest_year,
                "value": values[highest_year],
                "value_display": self._format_decimal(values[highest_year]),
            },
        }

    def _parse_annual_series(
        self,
        payload: dict[str, Any],
        max_year: int,
    ) -> tuple[dict[int, float], str, str]:
        """Baca payload `list/model/data` satu var tanpa rincian, jadi peta tahun → nilai."""
        if payload.get("status") != "OK":
            return {}, "", ""

        var_items = payload.get("var") or []
        vervar_items = payload.get("vervar") or []
        tahun_items = payload.get("tahun") or []
        datacontent = payload.get("datacontent") or {}
        if not var_items or not vervar_items or not tahun_items or not datacontent:
            return {}, "", ""

        var_id = str(var_items[0].get("val"))
        region_id = str(vervar_items[0].get("val"))
        turvar_ids = [str(item.get("val")) for item in (payload.get("turvar") or [])] or ["0"]
        period_ids = [str(item.get("val")) for item in (payload.get("turtahun") or [])] or ["0"]

        values: dict[int, float] = {}
        for item in tahun_items:
            point_year = self._to_int(item.get("label"))
            year_id = str(item.get("val"))
            if point_year is None or point_year > int(max_year):
                continue
            for turvar_id in turvar_ids:
                for period_id in period_ids:
                    # Key komposit dirakit, bukan di-parse: gabungan digit tanpa
                    # pemisah tidak bisa dipecah balik secara aman.
                    numeric = self._to_float(
                        datacontent.get(f"{region_id}{var_id}{turvar_id}{year_id}{period_id}")
                    )
                    if numeric is not None:
                        values[point_year] = numeric
                        break
                if point_year in values:
                    break

        return values, self._strip_html(var_items[0].get("note")), str(payload.get("last_update") or "").strip()

    def _normalize_kemiskinan_series(
        self,
        definition: DatasetDefinition,
        payloads: dict[str, dict[str, Any]],
        year: int,
    ) -> dict[str, Any]:
        """Rakit seri kemiskinan dari sheet manual jadi dataset per tahun.

        Sumbernya matriks lebar: kolom = tahun (menurun dari terbaru), baris =
        metrik. Dibalik jadi seri menaik supaya sebentuk dengan dataset lain,
        lalu dipotong sampai tahun terpilih agar selektor tahun tetap berarti.
        """
        payload = payloads.get("sheet") or {}
        if payload.get("status") != "OK":
            return self._build_unavailable_dataset(
                definition, year, payload.get("message", "Data kemiskinan tidak tersedia.")
            )

        rows = payload.get("rows") or []
        year_columns = self._parse_sheet_year_columns(rows, year)
        values_by_metric = self._parse_kemiskinan_rows(rows, year_columns)

        covered_years = sorted(
            {point_year for values in values_by_metric.values() for point_year in values}
        )
        if not covered_years:
            return self._build_unavailable_dataset(
                definition, year, "Tidak ada data kemiskinan sampai tahun ini."
            )

        series = [
            {
                "year": point_year,
                "year_label": str(point_year),
                **{
                    field: value
                    for metric in _KEMISKINAN_METRICS
                    for field, value in (
                        (metric["key"], values_by_metric[metric["key"]].get(point_year)),
                        (
                            f"{metric['key']}_display",
                            self._format_kemiskinan_value(
                                values_by_metric[metric["key"]].get(point_year), metric["format"]
                            ),
                        ),
                    )
                },
            }
            for point_year in covered_years
        ]

        latest_year = covered_years[-1]
        metrics = {
            metric["key"]: self._build_kemiskinan_metric(
                metric, values_by_metric[metric["key"]], covered_years
            )
            for metric in _KEMISKINAN_METRICS
        }

        return {
            "key": definition.key,
            "title": definition.title,
            "subtitle": definition.subtitle,
            "available": True,
            "year": year,
            "unit": "Persen / ribu jiwa / rupiah",
            "updated_at": "",
            "source": f"Sheet {payload.get('sheet_name') or 'Kemiskinan'}, olahan BPS Kabupaten Karawang",
            "series": series,
            "metrics": metrics,
            "latest_year": latest_year,
            "is_latest_fallback": latest_year != int(year),
        }

    def _parse_sheet_year_columns(self, rows: list[list[str]], max_year: int) -> dict[int, int]:
        """Peta tahun ke indeks kolom dari baris header, dibatasi sampai `max_year`."""
        header = rows[0] if rows else []
        columns: dict[int, int] = {}
        for index, cell in enumerate(header):
            point_year = self._to_int(cell)
            if point_year is None or not 1900 < point_year <= int(max_year):
                continue
            columns[point_year] = index
        return columns

    def _parse_kemiskinan_rows(
        self,
        rows: list[list[str]],
        year_columns: dict[int, int],
    ) -> dict[str, dict[int, float]]:
        values_by_metric: dict[str, dict[int, float]] = {
            metric["key"]: {} for metric in _KEMISKINAN_METRICS
        }

        current_label = ""
        for row in rows[1:]:
            if not row:
                continue
            # Sel label kosong berarti baris lanjutan dari metrik di atasnya
            # (P0 punya baris "Persen" dan "Ribuan Jiwa" di bawah satu label).
            current_label = self._clean_label(row[0]).upper() or current_label
            row_unit = self._clean_label(row[1] if len(row) > 1 else "").lower()

            metric = self._match_kemiskinan_metric(current_label, row_unit)
            if metric is None:
                continue

            for point_year, column_index in year_columns.items():
                if column_index >= len(row):
                    continue
                numeric = self._to_float_sheet(row[column_index])
                if numeric is not None:
                    values_by_metric[metric["key"]][point_year] = numeric

        return values_by_metric

    @staticmethod
    def _match_kemiskinan_metric(row_label: str, row_unit: str) -> dict[str, Any] | None:
        """Cocokkan satu baris sheet ke metrik, pakai satuan sebagai pembeda."""
        candidates = [
            metric for metric in _KEMISKINAN_METRICS if row_label.startswith(metric["row_label"])
        ]
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        # Label yang dipakai beberapa baris (P0) hanya bisa dipilah lewat satuan;
        # baris dengan satuan tak dikenal sengaja dibuang daripada salah masuk.
        return next((metric for metric in candidates if metric["row_unit"] == row_unit), None)

    def _build_kemiskinan_metric(
        self,
        metric: dict[str, Any],
        values: dict[int, float],
        covered_years: list[int],
    ) -> dict[str, Any]:
        filled_years = [
            point_year for point_year in covered_years if values.get(point_year) is not None
        ]
        base = {"key": metric["key"], "label": metric["label"], "unit": metric["unit"]}
        if not filled_years:
            return {**base, "latest_year": None, "value": None, "value_display": "\u2014", "change": {}}

        latest_year = filled_years[-1]
        latest_value = values[latest_year]
        change = (
            self._build_value_comparison(latest_value, values[filled_years[-2]])
            if len(filled_years) > 1
            else {}
        )
        if change:
            change["previous_year"] = filled_years[-2]
            change["previous_value_display"] = self._format_kemiskinan_value(
                values[filled_years[-2]], metric["format"]
            )
            # Delta ikut format dan satuan metriknya: selisih garis kemiskinan
            # adalah rupiah utuh, bukan "poin" dua desimal.
            change["delta_display"] = (
                f"{'+' if change['delta_value'] > 0 else ''}"
                f"{self._format_kemiskinan_value(change['delta_value'], metric['format'])}"
                f"{metric['delta_suffix']}"
            )

        lowest_year = min(filled_years, key=lambda point_year: values[point_year])
        highest_year = max(filled_years, key=lambda point_year: values[point_year])

        return {
            **base,
            "latest_year": latest_year,
            "value": latest_value,
            "value_display": self._format_kemiskinan_value(latest_value, metric["format"]),
            "change": change,
            "lowest": {
                "year": lowest_year,
                "value": values[lowest_year],
                "value_display": self._format_kemiskinan_value(values[lowest_year], metric["format"]),
            },
            "highest": {
                "year": highest_year,
                "value": values[highest_year],
                "value_display": self._format_kemiskinan_value(values[highest_year], metric["format"]),
            },
        }

    @classmethod
    def _format_kemiskinan_value(cls, value: float | None, fmt: str) -> str:
        if fmt == "integer":
            return cls._format_integer(value)
        if fmt == "decimal3":
            return cls._format_decimal(value, 3)
        return cls._format_decimal(value)

    @staticmethod
    def _to_float_sheet(value: Any) -> float | None:
        """Baca sel sheet: koma di sana pemisah ribuan ("617,901"), bukan desimal."""
        text = str(value or "").strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def _normalize_pdrb_triwulanan(
        self,
        definition: DatasetDefinition,
        payloads: dict[str, dict[str, Any]],
        year: int,
    ) -> dict[str, Any]:
        """Rakit satu dataset PDRB triwulanan dari payload ADHB, ADHK, dan distribusi.

        Ketiganya memakai endpoint `list/model/data` dengan bentuk identik, jadi
        parsing dilakukan sekali lalu digabung per periode dan per baris `vervar`.
        """
        parsed = {name: self._parse_pdrb_payload(payload) for name, payload in payloads.items()}
        self._resolve_unlabeled_periods(parsed)

        available_periods = {
            period_key
            for source in parsed.values()
            for period_key in source["values_by_period"]
        }
        if not available_periods:
            message = next(
                (source["message"] for source in parsed.values() if source["message"]),
                "Tidak ada data PDRB untuk tahun ini.",
            )
            return self._build_unavailable_dataset(definition, year, message)

        adhb = parsed.get("adhb") or {}
        adhk = parsed.get("adhk") or {}
        distribusi = parsed.get("distribusi") or {}
        label_source = next(
            (source for source in (adhb, adhk, distribusi) if source.get("labels")),
            {},
        )

        by_period = {
            period_key: self._build_pdrb_period_block(
                definition,
                label_source.get("labels") or [],
                adhb.get("values_by_period", {}).get(period_key, {}),
                adhk.get("values_by_period", {}).get(period_key, {}),
                distribusi.get("values_by_period", {}).get(period_key, {}),
            )
            for period_key in available_periods
        }
        by_period = {key: block for key, block in by_period.items() if block["rows"]}

        if not by_period:
            return self._build_unavailable_dataset(definition, year, "Tidak ada baris PDRB yang bisa dibaca.")

        periods = [
            {
                "period_key": period_key,
                "label": _PERIOD_LABELS[period_key],
                "available": period_key in by_period,
            }
            for period_key in _PERIOD_ORDER
        ]
        filled_periods = [period["period_key"] for period in periods if period["available"]]

        return {
            "key": definition.key,
            "title": definition.title,
            "subtitle": definition.subtitle,
            "available": True,
            "year": int(year),
            "unit": adhb.get("unit") or "Milyar Rupiah",
            "share_unit": distribusi.get("unit") or "Persen",
            "updated_at": adhb.get("last_update") or adhk.get("last_update") or "",
            "source": adhb.get("source") or "Web API BPS",
            "periods": periods,
            "default_period_key": filled_periods[-1],
            "by_period": by_period,
        }

    def _parse_pdrb_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Ubah satu payload `list/model/data` jadi nilai per periode per baris.

        Kunci `datacontent` dirakit `{vervar}{var}{turvar}{tahun}{turtahun}`; jangan
        di-parse balik karena penggabungan digit tanpa pemisah bersifat ambigu.
        """
        empty = {
            "message": "",
            "labels": [],
            "values_by_period": {},
            "unit": "",
            "source": "",
            "last_update": "",
        }

        if not isinstance(payload, dict) or payload.get("status") != "OK":
            message = str((payload or {}).get("message") or "Data tidak tersedia.")
            return {**empty, "message": message}

        var_items = payload.get("var") or []
        turvar_items = payload.get("turvar") or []
        vervar_items = payload.get("vervar") or []
        tahun_items = payload.get("tahun") or []
        turtahun_items = payload.get("turtahun") or []
        datacontent = payload.get("datacontent") or {}

        if not var_items or not turvar_items or not vervar_items or not tahun_items or not datacontent:
            return {**empty, "message": "Tidak ada data PDRB untuk tahun ini."}

        var_id = str(var_items[0].get("val"))
        turvar_id = str(turvar_items[0].get("val"))
        year_id = str(tahun_items[0].get("val"))

        labels = [
            (str(item.get("val")), self._clean_label(item.get("label")))
            for item in vervar_items
        ]

        values_by_period: dict[str, dict[str, float]] = {}
        for turtahun in turtahun_items:
            turtahun_id = str(turtahun.get("val"))
            # `0` = periode tak berlabel triwulan; var 617 memakainya walau isinya
            # triwulanan. Ditandai dulu, dipetakan belakangan oleh payload saudara.
            period_key = _PERIOD_KEY_BY_TURTAHUN_ID.get(turtahun_id, _UNLABELED_PERIOD_KEY)

            values: dict[str, float] = {}
            for vervar_id, _ in labels:
                numeric_value = self._to_float(
                    datacontent.get(f"{vervar_id}{var_id}{turvar_id}{year_id}{turtahun_id}")
                )
                if numeric_value is not None:
                    values[vervar_id] = numeric_value

            # Periode dianggap tersedia hanya kalau benar-benar menghasilkan angka,
            # bukan sekadar terdaftar di `turtahun`.
            if values:
                values_by_period[period_key] = values

        return {
            "message": "" if values_by_period else "Tidak ada data PDRB untuk tahun ini.",
            "labels": labels,
            "values_by_period": values_by_period,
            "unit": self._strip_html(var_items[0].get("unit")),
            "source": self._strip_html(var_items[0].get("note")) or "Web API BPS",
            "last_update": str(payload.get("last_update") or "").strip(),
        }

    @staticmethod
    def _resolve_unlabeled_periods(parsed: dict[str, dict[str, Any]]) -> None:
        """Petakan periode tak berlabel (`turtahun` = 0) ke triwulan yang benar.

        Var 617 melaporkan `turtahun` `0/Tahun` padahal nilainya identik dengan
        triwulan yang dilaporkan var 618/619. Pemetaan hanya dilakukan kalau
        payload saudaranya menunjuk tepat satu periode — kalau lebih dari satu,
        pasangannya tidak bisa ditentukan dan datanya dibuang, bukan ditebak.
        """
        labeled_periods = {
            period_key
            for source in parsed.values()
            for period_key in source["values_by_period"]
            if period_key != _UNLABELED_PERIOD_KEY
        }

        for source in parsed.values():
            values = source["values_by_period"].pop(_UNLABELED_PERIOD_KEY, None)
            if values is None:
                continue
            if len(labeled_periods) == 1:
                source["values_by_period"][next(iter(labeled_periods))] = values
            else:
                print(
                    "[BPS] Periode tak berlabel pada payload PDRB dilewati: "
                    f"kandidat periode = {sorted(labeled_periods) or 'kosong'}."
                )

    def _build_pdrb_period_block(
        self,
        definition: DatasetDefinition,
        labels: list[tuple[str, str]],
        adhb_values: dict[str, float],
        adhk_values: dict[str, float],
        share_values: dict[str, float],
    ) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        total_row: dict[str, Any] | None = None

        for index, (vervar_id, label) in enumerate(labels):
            adhb_value = adhb_values.get(vervar_id)
            adhk_value = adhk_values.get(vervar_id)
            if adhb_value is None and adhk_value is None:
                continue

            row = self._build_pdrb_row(
                code=(
                    _LAPANGAN_USAHA_CODES[index]
                    if definition.use_category_codes and index < len(_LAPANGAN_USAHA_CODES)
                    else ""
                ),
                label=label,
                adhb=adhb_value,
                adhk=adhk_value,
                share=share_values.get(vervar_id),
            )

            # Var 617/618 menyertakan baris agregat; var 610/611 tidak.
            if label == _PDRB_TOTAL_LABEL:
                total_row = row
                continue

            rows.append(row)

        rows.sort(key=lambda item: item.get("adhb") if item.get("adhb") is not None else -1, reverse=True)

        if total_row is None:
            total_row = self._build_pdrb_row(
                code="",
                label=_PDRB_TOTAL_LABEL,
                adhb=self._sum_optional(row.get("adhb") for row in rows),
                adhk=self._sum_optional(row.get("adhk") for row in rows),
                share=self._sum_optional(row.get("share") for row in rows),
            )

        total_adhb = total_row.get("adhb")
        for row in rows:
            if row.get("share") is None and row.get("adhb") is not None and total_adhb:
                row["share"] = row["adhb"] / total_adhb * 100
                row["share_display"] = self._format_decimal(row["share"])

        return {
            "total": total_row,
            "rows": rows,
            "top_rows": rows[:_PDRB_TOP_LIMIT],
        }

    def _build_pdrb_row(
        self,
        *,
        code: str,
        label: str,
        adhb: float | None,
        adhk: float | None,
        share: float | None,
    ) -> dict[str, Any]:
        # Indeks harga implisit = deflator PDRB per baris, basis 2010 = 100.
        implicit_index = (adhb / adhk * 100) if (adhb is not None and adhk) else None

        return {
            "code": code,
            "label": label,
            "adhb": adhb,
            "adhk": adhk,
            "share": share,
            "implicit_index": implicit_index,
            "adhb_display": self._format_decimal(adhb),
            "adhk_display": self._format_decimal(adhk),
            "share_display": self._format_decimal(share),
            "implicit_index_display": self._format_decimal(implicit_index),
        }

    @staticmethod
    def _sum_optional(values: Any) -> float | None:
        numbers = [value for value in values if value is not None]
        return sum(numbers) if numbers else None

    def _build_unavailable_dataset(
        self,
        definition: DatasetDefinition,
        year: int,
        message: str,
    ) -> dict[str, Any]:
        return {
            "key": definition.key,
            "title": definition.title,
            "subtitle": definition.subtitle,
            "available": False,
            "year": int(year),
            "message": message or "Data tidak tersedia untuk tahun ini.",
            "rows": [],
            "top_rows": [],
            "periods": [],
            "by_period": {},
        }

    def _is_complete_bundle(self, datasets: dict[str, Any]) -> bool:
        keys = set(datasets.keys())
        required = {definition.key for definition in _DATASET_DEFINITIONS}
        return required.issubset(keys)

    @staticmethod
    def _read_cache(year: int) -> dict[str, Any] | None:
        with _YEAR_CACHE_LOCK:
            cached = _YEAR_CACHE.get(year)
            if not cached:
                return None
            if time.time() - cached["ts"] > _CACHE_TTL_SECONDS:
                _YEAR_CACHE.pop(year, None)
                return None
            return cached["value"]

    @staticmethod
    def _write_cache(year: int, datasets: dict[str, Any]) -> None:
        with _YEAR_CACHE_LOCK:
            _YEAR_CACHE[year] = {
                "ts": time.time(),
                "value": deepcopy(datasets),
            }

    @staticmethod
    def _build_value_comparison(
        current_value: float | None,
        previous_value: float | None,
        *,
        unit_suffix: str = "",
    ) -> dict[str, Any]:
        if current_value is None or previous_value is None:
            return {}

        delta_value = current_value - previous_value
        delta_percentage = None if previous_value == 0 else (delta_value / previous_value) * 100
        return {
            "current_value": current_value,
            "previous_value": previous_value,
            "delta_value": delta_value,
            "delta_percentage": delta_percentage,
            "delta_display": f"{OfficialStatisticsService._format_signed_decimal(delta_value)}{unit_suffix}",
            "delta_percentage_display": OfficialStatisticsService._format_signed_percent(delta_percentage),
        }

    @staticmethod
    def _clean_label(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip())

    @staticmethod
    def _strip_html(value: Any) -> str:
        raw = html.unescape(str(value or "")).replace("<br>", " ").replace("<br/>", " ")
        clean = re.sub(r"<[^>]+>", " ", raw)
        return re.sub(r"\s+", " ", clean).strip(" -\n\t")

    @staticmethod
    def _to_int(value: Any) -> int | None:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _format_decimal(value: float | None, digits: int = 2) -> str:
        if value is None:
            return "—"
        return f"{value:,.{digits}f}".replace(",", "_").replace(".", ",").replace("_", ".")

    @staticmethod
    def _format_integer(value: float | None) -> str:
        if value is None:
            return "—"
        return f"{int(round(value)):,}".replace(",", ".")

    @staticmethod
    def _format_signed_decimal(value: float | None, digits: int = 2) -> str:
        if value is None:
            return "—"
        sign = "+" if value > 0 else ""
        return f"{sign}{OfficialStatisticsService._format_decimal(value, digits)}"

    @staticmethod
    def _format_signed_percent(value: float | None, digits: int = 2) -> str:
        if value is None:
            return "—"
        return f"{OfficialStatisticsService._format_signed_decimal(value, digits)}%"

    @staticmethod
    def _normalize_page_year(year: int | None) -> int:
        if year is None:
            return _DEFAULT_PAGE_YEAR
        try:
            parsed = int(year)
        except (TypeError, ValueError):
            return _DEFAULT_PAGE_YEAR
        if 2000 <= parsed <= 2100:
            return parsed
        return _DEFAULT_PAGE_YEAR

    @staticmethod
    def _normalize_topics(topics: set[str] | None) -> set[str]:
        if not topics:
            return set(_AI_TOPIC_DEFAULTS)
        return {topic for topic in topics if topic in _AI_TOPIC_DEFAULTS} or set(_AI_TOPIC_DEFAULTS)

    @staticmethod
    def _now_iso() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


_official_statistics_service = OfficialStatisticsService()


def get_official_statistics_dashboard_payload(
    year: int | None = None,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    return _official_statistics_service.get_dashboard_payload(year, force_refresh=force_refresh)


def get_official_statistics_ai_context(
    requested_year: int | None = None,
    *,
    topics: set[str] | None = None,
) -> dict[str, Any]:
    return _official_statistics_service.build_ai_context(requested_year=requested_year, topics=topics)


def detect_official_statistics_chat_topics(query: str) -> set[str]:
    return _official_statistics_service.detect_chat_topics(query)


def detect_official_statistics_requested_year(text: str) -> int | None:
    return _official_statistics_service.detect_requested_year(text)
