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
from repositories.official_statistics import (
    load_official_statistics_year_snapshots,
    upsert_official_statistics_snapshots,
)

_PAGE_SUPPORTED_YEARS = (2025, 2024)
_DEFAULT_PAGE_YEAR = _PAGE_SUPPORTED_YEARS[0]
_CACHE_TTL_SECONDS = 30 * 60
_PDRB_TOP_LIMIT = 8
_PDRB_PENGELUARAN_TOP_LIMIT = 4
_AI_TOPIC_DEFAULTS = ("pdrb", "kemiskinan", "pengangguran")

_QUARTER_KEY_BY_ID = {
    "832": "q1",
    "833": "q2",
    "834": "q3",
    "835": "q4",
    "836": "total",
}

_YEAR_CACHE_LOCK = Lock()
_YEAR_CACHE: dict[int, dict[str, Any]] = {}


@dataclass(frozen=True)
class DatasetDefinition:
    key: str
    title: str
    subtitle: str
    period_key: str
    fetch_method: str
    normalizer_method: str


_DATASET_DEFINITIONS: tuple[DatasetDefinition, ...] = (
    DatasetDefinition(
        key="pdrb_adhk",
        title="PDRB ADHK Lapangan Usaha",
        subtitle="Atas Dasar Harga Konstan 2010",
        period_key="annual",
        fetch_method="fetch_pdrb_adhk",
        normalizer_method="_normalize_pdrb_lapangan_usaha",
    ),
    DatasetDefinition(
        key="pdrb_adhb",
        title="PDRB ADHB Lapangan Usaha",
        subtitle="Atas Dasar Harga Berlaku",
        period_key="annual",
        fetch_method="fetch_pdrb_adhb",
        normalizer_method="_normalize_pdrb_lapangan_usaha",
    ),
    DatasetDefinition(
        key="tpt_tpak",
        title="TPT dan TPAK",
        subtitle="Perbandingan menurut jenis kelamin",
        period_key="annual",
        fetch_method="fetch_tpt_tpak",
        normalizer_method="_normalize_tpt_tpak",
    ),
    DatasetDefinition(
        key="kemiskinan",
        title="Kemiskinan",
        subtitle="Eks Karesidenan Pekalongan",
        period_key="annual",
        fetch_method="fetch_kemiskinan",
        normalizer_method="_normalize_kemiskinan",
    ),
    DatasetDefinition(
        key="pdrb_pengeluaran_adhk",
        title="PDRB Pengeluaran Triwulanan ADHK",
        subtitle="Atas Dasar Harga Konstan 2010",
        period_key="quarterly_bundle",
        fetch_method="fetch_pdrb_pengeluaran_adhk",
        normalizer_method="_normalize_pdrb_pengeluaran",
    ),
    DatasetDefinition(
        key="pdrb_pengeluaran_adhb",
        title="PDRB Pengeluaran Triwulanan ADHB",
        subtitle="Atas Dasar Harga Berlaku",
        period_key="quarterly_bundle",
        fetch_method="fetch_pdrb_pengeluaran_adhb",
        normalizer_method="_normalize_pdrb_pengeluaran",
    ),
)


class OfficialStatisticsService:
    """Orkestrasi fetch, normalisasi, cache, dan persistence statistik resmi BPS."""

    def __init__(self, bps_client: BPSWebApiClient | None = None):
        self._client = bps_client or BPSWebApiClient()

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
            )
        ):
            topics.add("pdrb")

        if any(keyword in text for keyword in ("kemiskinan", "miskin", "garis kemiskinan", "bansos", "kesejahteraan")):
            topics.add("kemiskinan")

        if any(keyword in text for keyword in ("pengangguran", "tpt", "tpak", "angkatan kerja", "tenaga kerja", "phk", "lowongan kerja")):
            topics.add("pengangguran")

        if topics:
            return topics

        if any(keyword in text for keyword in ("statistik resmi", "data resmi", "bps", "ekonomi tegal")):
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

            persisted = load_official_statistics_year_snapshots(normalized_year)
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
            raw_payload = self._safe_fetch_raw_payload(definition, year)
            normalized_dataset = self._safe_normalize_dataset(definition, raw_payload, year)
            datasets[definition.key] = normalized_dataset
            snapshots.append(self._build_snapshot_row(definition, year, raw_payload, normalized_dataset))

        return datasets, snapshots

    def _safe_fetch_raw_payload(self, definition: DatasetDefinition, year: int) -> dict[str, Any]:
        try:
            fetcher = getattr(self._client, definition.fetch_method)
            return fetcher(year)
        except Exception as exc:
            print(f"[BPS] Gagal fetch {definition.key} tahun {year}: {exc}")
            return {
                "status": "ERROR",
                "message": str(exc),
            }

    def _safe_normalize_dataset(
        self,
        definition: DatasetDefinition,
        raw_payload: dict[str, Any],
        year: int,
    ) -> dict[str, Any]:
        try:
            normalizer = getattr(self, definition.normalizer_method)
            return normalizer(definition, raw_payload, year)
        except Exception as exc:
            print(f"[BPS] Gagal normalisasi {definition.key} tahun {year}: {exc}")
            return self._build_unavailable_dataset(definition, year, str(exc))

    def _build_snapshot_row(
        self,
        definition: DatasetDefinition,
        year: int,
        raw_payload: dict[str, Any],
        normalized_dataset: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "dataset_key": definition.key,
            "year": int(year),
            "period_key": definition.period_key,
            "title": definition.title,
            "source": normalized_dataset.get("source"),
            "updated_at_source_text": normalized_dataset.get("updated_at"),
            "raw_payload": raw_payload,
            "normalized_payload": normalized_dataset,
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
        if dataset_key.startswith("pdrb_pengeluaran_"):
            return self._build_pdrb_pengeluaran_comparison(current_dataset, previous_dataset)
        if dataset_key.startswith("pdrb_"):
            return self._build_pdrb_lapangan_usaha_comparison(current_dataset, previous_dataset)
        if dataset_key == "tpt_tpak":
            return self._build_tpt_tpak_comparison(current_dataset, previous_dataset)
        if dataset_key == "kemiskinan":
            return self._build_kemiskinan_comparison(current_dataset, previous_dataset)
        return {}

    def _build_pdrb_lapangan_usaha_comparison(
        self,
        current_dataset: dict[str, Any],
        previous_dataset: dict[str, Any],
    ) -> dict[str, Any]:
        summary = self._build_value_comparison(
            current_dataset.get("total_value"),
            previous_dataset.get("total_value"),
            unit_suffix=" miliar",
        )
        summary.update(
            {
                "previous_year": previous_dataset.get("year"),
                "previous_total_display": previous_dataset.get("total_display", "—"),
            }
        )
        return summary

    def _build_tpt_tpak_comparison(
        self,
        current_dataset: dict[str, Any],
        previous_dataset: dict[str, Any],
    ) -> dict[str, Any]:
        indicators: dict[str, Any] = {}
        for key in ("tpak", "tpt"):
            current_indicator = (current_dataset.get("indicators") or {}).get(key, {})
            previous_indicator = (previous_dataset.get("indicators") or {}).get(key, {})
            indicators[key] = self._build_value_comparison(
                current_indicator.get("total"),
                previous_indicator.get("total"),
                unit_suffix=" poin",
            )
            indicators[key]["previous_total_display"] = previous_indicator.get("total_display", "—")

        return {
            "previous_year": previous_dataset.get("year"),
            "indicators": indicators,
        }

    def _build_kemiskinan_comparison(
        self,
        current_dataset: dict[str, Any],
        previous_dataset: dict[str, Any],
    ) -> dict[str, Any]:
        current_metrics = current_dataset.get("tegal_metrics") or {}
        previous_metrics = previous_dataset.get("tegal_metrics") or {}

        return {
            "previous_year": previous_dataset.get("year"),
            "poverty_rate": self._build_value_comparison(
                current_metrics.get("poverty_rate"),
                previous_metrics.get("poverty_rate"),
                unit_suffix=" poin",
            ),
            "poor_population": self._build_value_comparison(
                current_metrics.get("poor_population"),
                previous_metrics.get("poor_population"),
                unit_suffix=" ribu jiwa",
            ),
            "poverty_line": self._build_value_comparison(
                current_metrics.get("poverty_line"),
                previous_metrics.get("poverty_line"),
                unit_suffix=" rupiah",
            ),
        }

    def _build_pdrb_pengeluaran_comparison(
        self,
        current_dataset: dict[str, Any],
        previous_dataset: dict[str, Any],
    ) -> dict[str, Any]:
        current_quarters = {row["quarter_key"]: row for row in current_dataset.get("quarter_series") or []}
        previous_quarters = {row["quarter_key"]: row for row in previous_dataset.get("quarter_series") or []}

        comparison_quarters = []
        for quarter_key in ("q1", "q2", "q3", "q4", "total"):
            current_row = current_quarters.get(quarter_key)
            previous_row = previous_quarters.get(quarter_key)
            if not current_row:
                continue

            value_comparison = self._build_value_comparison(
                current_row.get("value"),
                previous_row.get("value") if previous_row else None,
                unit_suffix=" miliar",
            )
            comparison_quarters.append(
                {
                    "quarter_key": quarter_key,
                    "label": current_row.get("label"),
                    "current_display": current_row.get("display_value", "—"),
                    "previous_display": previous_row.get("display_value", "—") if previous_row else "—",
                    **value_comparison,
                }
            )

        strongest_growth = self._pick_strongest_quarter_change(comparison_quarters)
        annual_summary = next((item for item in comparison_quarters if item["quarter_key"] == "total"), {})
        return {
            "previous_year": previous_dataset.get("year"),
            "annual_summary": annual_summary,
            "comparison_quarters": comparison_quarters,
            "strongest_growth": strongest_growth,
        }

    def _pick_strongest_quarter_change(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        quarter_rows = [
            row for row in rows
            if row.get("quarter_key") in {"q1", "q2", "q3", "q4"}
            and row.get("delta_percentage") is not None
        ]
        if not quarter_rows:
            return {}
        return max(quarter_rows, key=lambda row: row.get("delta_percentage") or 0)

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
        lapangan_adhk = datasets.get("pdrb_adhk") or {}
        lapangan_adhb = datasets.get("pdrb_adhb") or {}
        pengeluaran_adhk = datasets.get("pdrb_pengeluaran_adhk") or {}
        pengeluaran_adhb = datasets.get("pdrb_pengeluaran_adhb") or {}

        if not any(dataset.get("available") for dataset in (lapangan_adhk, lapangan_adhb, pengeluaran_adhk, pengeluaran_adhb)):
            return ""

        lines = [f"Statistik resmi BPS tahun {year} untuk PDRB Kabupaten Tegal:"]

        if lapangan_adhk.get("available"):
            lines.append(self._build_pdrb_lapangan_ai_line(lapangan_adhk, "ADHK"))
        if lapangan_adhb.get("available"):
            lines.append(self._build_pdrb_lapangan_ai_line(lapangan_adhb, "ADHB"))
        if pengeluaran_adhk.get("available"):
            lines.append(self._build_pdrb_pengeluaran_ai_line(pengeluaran_adhk, "ADHK"))
        if pengeluaran_adhb.get("available"):
            lines.append(self._build_pdrb_pengeluaran_ai_line(pengeluaran_adhb, "ADHB"))

        lines.append(
            "Gunakan statistik resmi ini sebagai baseline. Jika pengguna menanyakan penyebab perubahan, kaitkan angka resmi dengan berita relevan dan jelaskan apakah dukungan berita cukup atau masih indikatif."
        )
        return "\n".join(lines)

    def _build_pdrb_lapangan_ai_line(self, dataset: dict[str, Any], label: str) -> str:
        top_sectors = ", ".join(
            f"{row['label']} ({row['display_value']})"
            for row in (dataset.get("top_rows") or [])[:3]
        )
        comparison = dataset.get("comparison") or {}
        if comparison.get("delta_display") and comparison.get("previous_year"):
            return (
                f"- PDRB {label} total {dataset.get('total_display', '—')} miliar rupiah, berubah {comparison.get('delta_display')} "
                f"({comparison.get('delta_percentage_display', '—')}) dibanding {comparison.get('previous_year')}; sektor utama: {top_sectors}."
            )
        return f"- PDRB {label} total {dataset.get('total_display', '—')} miliar rupiah; sektor utama: {top_sectors}."

    def _build_pdrb_pengeluaran_ai_line(self, dataset: dict[str, Any], label: str) -> str:
        comparison = dataset.get("comparison") or {}
        annual_summary = comparison.get("annual_summary") or {}
        top_component = (dataset.get("top_components") or [{}])[0]
        strongest_growth = comparison.get("strongest_growth") or {}

        line = (
            f"- PDRB Pengeluaran {label} total {dataset.get('annual_total_display', '—')} miliar rupiah; "
            f"komponen terbesar {top_component.get('label', '—')} ({top_component.get('total_display', '—')})."
        )

        if annual_summary.get("delta_display") and comparison.get("previous_year"):
            line = (
                f"- PDRB Pengeluaran {label} total {dataset.get('annual_total_display', '—')} miliar rupiah, berubah {annual_summary.get('delta_display')} "
                f"({annual_summary.get('delta_percentage_display', '—')}) dibanding {comparison.get('previous_year')}; "
                f"komponen terbesar {top_component.get('label', '—')} ({top_component.get('total_display', '—')})."
            )

        if strongest_growth.get("label") and strongest_growth.get("delta_percentage_display"):
            line += (
                f" Pertumbuhan triwulanan paling kuat terlihat pada {strongest_growth.get('label')} "
                f"({strongest_growth.get('delta_percentage_display')})."
            )

        return line

    def _build_tpt_ai_block(self, datasets: dict[str, Any], year: int) -> str:
        dataset = datasets.get("tpt_tpak") or {}
        if not dataset.get("available"):
            return ""

        tpak = dataset.get("indicators") or {}
        tpak_value = tpak.get("tpak", {})
        tpt_value = tpak.get("tpt", {})
        comparison = dataset.get("comparison") or {}
        tpak_comparison = (comparison.get("indicators") or {}).get("tpak", {})
        tpt_comparison = (comparison.get("indicators") or {}).get("tpt", {})

        lines = [f"Statistik resmi BPS tahun {year} untuk ketenagakerjaan Kabupaten Tegal:"]
        lines.append(
            f"- TPAK total {tpak_value.get('total_display', '—')} persen; laki-laki {tpak_value.get('male_display', '—')} persen; perempuan {tpak_value.get('female_display', '—')} persen."
        )
        if tpak_comparison.get("delta_display") and comparison.get("previous_year"):
            lines.append(
                f"- Dibanding {comparison.get('previous_year')}, TPAK berubah {tpak_comparison.get('delta_display')} ({tpak_comparison.get('delta_percentage_display', '—')})."
            )
        lines.append(
            f"- TPT total {tpt_value.get('total_display', '—')} persen; laki-laki {tpt_value.get('male_display', '—')} persen; perempuan {tpt_value.get('female_display', '—')} persen."
        )
        if tpt_comparison.get("delta_display") and comparison.get("previous_year"):
            lines.append(
                f"- Dibanding {comparison.get('previous_year')}, TPT berubah {tpt_comparison.get('delta_display')} ({tpt_comparison.get('delta_percentage_display', '—')})."
            )
        lines.append(
            "Gunakan angka resmi ini sebagai baseline. Saat menjelaskan penyebab perubahan, kaitkan dengan berita tentang rekrutmen, PHK, pelatihan kerja, atau pergeseran sektor kerja."
        )
        return "\n".join(lines)

    def _build_kemiskinan_ai_block(self, datasets: dict[str, Any], year: int) -> str:
        dataset = datasets.get("kemiskinan") or {}
        if not dataset.get("available"):
            return ""

        tegal_metrics = dataset.get("tegal_metrics") or {}
        comparison = dataset.get("comparison") or {}
        poverty_rate_comparison = comparison.get("poverty_rate") or {}
        poor_population_comparison = comparison.get("poor_population") or {}

        lines = [f"Statistik resmi BPS tahun {year} untuk kemiskinan Kabupaten Tegal:"]
        lines.append(
            (
                f"- Kabupaten Tegal: garis kemiskinan {tegal_metrics.get('poverty_line_display', '—')} rupiah/kapita/bulan, "
                f"jumlah penduduk miskin {tegal_metrics.get('poor_population_display', '—')} ribu jiwa, "
                f"persentase penduduk miskin {tegal_metrics.get('poverty_rate_display', '—')} persen."
            )
        )
        if poverty_rate_comparison.get("delta_display") and comparison.get("previous_year"):
            lines.append(
                f"- Dibanding {comparison.get('previous_year')}, persentase penduduk miskin berubah {poverty_rate_comparison.get('delta_display')} ({poverty_rate_comparison.get('delta_percentage_display', '—')})."
            )
        if poor_population_comparison.get("delta_display") and comparison.get("previous_year"):
            lines.append(
                f"- Jumlah penduduk miskin berubah {poor_population_comparison.get('delta_display')} ({poor_population_comparison.get('delta_percentage_display', '—')}) dibanding {comparison.get('previous_year')}."
            )
        lines.append(
            "Gunakan angka resmi ini sebagai acuan utama. Jika menjelaskan penyebab, kaitkan dengan berita tentang daya beli, pangan, bansos, pekerjaan, atau tekanan biaya hidup."
        )
        return "\n".join(lines)

    def _normalize_pdrb_lapangan_usaha(
        self,
        definition: DatasetDefinition,
        payload: dict[str, Any],
        year: int,
    ) -> dict[str, Any]:
        if payload.get("status") != "OK":
            return self._build_unavailable_dataset(definition, year, payload.get("message", "Data tidak tersedia."))

        container = payload.get("data") or []
        if len(container) < 2 or not isinstance(container[1], dict):
            return self._build_unavailable_dataset(definition, year, "Struktur data PDRB tidak dikenali.")

        content = container[1]
        data_rows = content.get("data") or []
        column_map = content.get("kolom") or {}
        column_key = next(iter(column_map.keys()), "")

        if not data_rows or not column_key:
            return self._build_unavailable_dataset(definition, year, "Tidak ada data untuk tahun ini.")

        rows: list[dict[str, Any]] = []
        total_display = "—"
        total_value = None
        total_code = ""

        for row in data_rows:
            variables = row.get("variables") or {}
            value_info = variables.get(column_key) or {}
            display_value = str(value_info.get("value_raw") or "").strip()
            numeric_value = self._parse_localized_number(display_value)
            label_raw = self._clean_label(row.get("label_raw"))

            if label_raw.lower() == "produk domestik bruto":
                total_display = display_value or "—"
                total_value = numeric_value
                total_code = str(value_info.get("value_code") or "").strip()
                continue

            if not label_raw or numeric_value is None:
                continue

            code, label = self._split_sector_label(label_raw)
            rows.append(
                {
                    "code": code,
                    "label": label,
                    "full_label": label_raw,
                    "display_value": display_value,
                    "value": numeric_value,
                }
            )

        rows.sort(key=lambda item: item["value"], reverse=True)

        note_map = content.get("keterangan_data") or {}
        value_note = self._strip_html(note_map.get(total_code, "")) if total_code else ""
        latest_change = self._extract_latest_change(content.get("change_log") or [])

        return {
            "key": definition.key,
            "title": definition.title,
            "subtitle": definition.subtitle,
            "available": bool(rows),
            "year": int(content.get("tahun_data") or year),
            "unit": "Miliar rupiah",
            "updated_at": str(content.get("table_updated") or content.get("created") or "").strip(),
            "source": self._strip_html(content.get("sumber")) or "Web API BPS",
            "total_display": total_display,
            "total_value": total_value,
            "top_rows": rows[:_PDRB_TOP_LIMIT],
            "rows": rows,
            "latest_change": latest_change,
            "value_note": value_note,
        }

    def _normalize_tpt_tpak(
        self,
        definition: DatasetDefinition,
        payload: dict[str, Any],
        year: int,
    ) -> dict[str, Any]:
        if payload.get("status") != "OK":
            return self._build_unavailable_dataset(definition, year, payload.get("message", "Data tidak tersedia."))

        var_items = payload.get("var") or []
        turvar_items = payload.get("turvar") or []
        vervar_items = payload.get("vervar") or []
        tahun_items = payload.get("tahun") or []
        turtahun_items = payload.get("turtahun") or []
        datacontent = payload.get("datacontent") or {}

        if not var_items or not turvar_items or not vervar_items or not tahun_items or not datacontent:
            return self._build_unavailable_dataset(definition, year, "Tidak ada data TPT/TPAK untuk tahun ini.")

        var_id = str(var_items[0].get("val"))
        year_id = str(tahun_items[0].get("val"))
        period_id = str((turtahun_items[0] if turtahun_items else {}).get("val", 0))

        gender_map = {str(item.get("val")): str(item.get("label") or "") for item in turvar_items}
        indicator_map = {str(item.get("val")): str(item.get("label") or "") for item in vervar_items}

        indicators: dict[str, Any] = {}
        chart_groups: list[dict[str, Any]] = []

        for indicator_id, indicator_label in indicator_map.items():
            indicator_key = "tpak" if "TPAK" in indicator_label else "tpt"
            values_by_gender: dict[str, float | None] = {}

            for gender_id, gender_label in gender_map.items():
                composite_key = f"{indicator_id}{var_id}{gender_id}{year_id}{period_id}"
                numeric_value = self._to_float(datacontent.get(composite_key))
                values_by_gender[gender_label] = numeric_value
                chart_groups.append(
                    {
                        "indicator": indicator_label,
                        "indicator_key": indicator_key,
                        "gender": gender_label,
                        "value": numeric_value,
                    }
                )

            indicators[indicator_key] = {
                "label": indicator_label,
                "male": values_by_gender.get("Laki-laki"),
                "female": values_by_gender.get("Perempuan"),
                "total": values_by_gender.get("Jumlah"),
                "male_display": self._format_decimal(values_by_gender.get("Laki-laki")),
                "female_display": self._format_decimal(values_by_gender.get("Perempuan")),
                "total_display": self._format_decimal(values_by_gender.get("Jumlah")),
            }

        return {
            "key": definition.key,
            "title": definition.title,
            "subtitle": definition.subtitle,
            "available": bool(indicators),
            "year": year,
            "unit": "Persen",
            "updated_at": str(payload.get("last_update") or "").strip(),
            "source": self._strip_html(var_items[0].get("note")) or "Web API BPS",
            "indicators": indicators,
            "chart_groups": chart_groups,
        }

    def _normalize_kemiskinan(
        self,
        definition: DatasetDefinition,
        payload: dict[str, Any],
        year: int,
    ) -> dict[str, Any]:
        if payload.get("status") != "OK":
            return self._build_unavailable_dataset(definition, year, payload.get("message", "Data tidak tersedia."))

        var_items = payload.get("var") or []
        turvar_items = payload.get("turvar") or []
        vervar_items = payload.get("vervar") or []
        tahun_items = payload.get("tahun") or []
        turtahun_items = payload.get("turtahun") or []
        datacontent = payload.get("datacontent") or {}

        if not var_items or not turvar_items or not vervar_items or not tahun_items or not datacontent:
            return self._build_unavailable_dataset(definition, year, "Tidak ada data kemiskinan untuk tahun ini.")

        var_id = str(var_items[0].get("val"))
        year_id = str(tahun_items[0].get("val"))
        period_id = str((turtahun_items[0] if turtahun_items else {}).get("val", 0))
        metric_map = {str(item.get("val")): str(item.get("label") or "") for item in turvar_items}

        rows: list[dict[str, Any]] = []
        tegal_metrics: dict[str, Any] = {}

        for area in vervar_items:
            area_id = str(area.get("val"))
            label = str(area.get("label") or "").strip()
            row: dict[str, Any] = {"label": label}

            for metric_id, metric_label in metric_map.items():
                composite_key = f"{area_id}{var_id}{metric_id}{year_id}{period_id}"
                numeric_value = self._to_float(datacontent.get(composite_key))
                if "Garis Kemiskinan" in metric_label:
                    row["poverty_line"] = numeric_value
                elif "Jumlah Penduduk Miskin" in metric_label:
                    row["poor_population"] = numeric_value
                elif "Persentase Penduduk Miskin" in metric_label:
                    row["poverty_rate"] = numeric_value

            if any(row.get(name) is not None for name in ("poverty_line", "poor_population", "poverty_rate")):
                row["poverty_line_display"] = self._format_integer(row.get("poverty_line"))
                row["poor_population_display"] = self._format_decimal(row.get("poor_population"))
                row["poverty_rate_display"] = self._format_decimal(row.get("poverty_rate"))
                rows.append(row)

            if label == "Kabupaten Tegal":
                tegal_metrics = row

        comparison_rows = sorted(
            [row for row in rows if row.get("label") != "Jawa Tengah"],
            key=lambda item: item.get("poverty_rate") or -1,
            reverse=True,
        )

        highest_area = comparison_rows[0] if comparison_rows else {}

        return {
            "key": definition.key,
            "title": definition.title,
            "subtitle": definition.subtitle,
            "available": bool(rows),
            "year": year,
            "unit": "Persen / ribu jiwa / rupiah",
            "updated_at": str(payload.get("last_update") or "").strip(),
            "source": self._strip_html(var_items[0].get("note")) or "Web API BPS",
            "tegal_metrics": tegal_metrics,
            "comparison_rows": comparison_rows,
            "highest_poverty_area": {
                "label": highest_area.get("label"),
                "value": highest_area.get("poverty_rate"),
                "display_value": highest_area.get("poverty_rate_display"),
            }
            if highest_area
            else {},
        }

    def _normalize_pdrb_pengeluaran(
        self,
        definition: DatasetDefinition,
        payload: dict[str, Any],
        year: int,
    ) -> dict[str, Any]:
        if payload.get("status") != "OK":
            return self._build_unavailable_dataset(definition, year, payload.get("message", "Data tidak tersedia."))

        var_items = payload.get("var") or []
        turvar_items = payload.get("turvar") or []
        vervar_items = payload.get("vervar") or []
        tahun_items = payload.get("tahun") or []
        turtahun_items = payload.get("turtahun") or []
        datacontent = payload.get("datacontent") or {}

        if not var_items or not turvar_items or not vervar_items or not tahun_items or not datacontent:
            return self._build_unavailable_dataset(definition, year, "Tidak ada data PDRB pengeluaran untuk tahun ini.")

        var_id = str(var_items[0].get("val"))
        year_id = str(tahun_items[0].get("val"))
        period_id = str((turtahun_items[0] if turtahun_items else {}).get("val", 0))

        quarter_order = [
            {
                "quarter_id": str(item.get("val")),
                "quarter_key": _QUARTER_KEY_BY_ID.get(str(item.get("val")), f"period_{item.get('val')}"),
                "label": str(item.get("label") or ""),
            }
            for item in turvar_items
        ]

        component_rows: list[dict[str, Any]] = []
        pdrb_total_row: dict[str, Any] = {}

        for component in vervar_items:
            component_id = str(component.get("val"))
            component_label = str(component.get("label") or "").strip()
            values: dict[str, float | None] = {}
            displays: dict[str, str] = {}

            for quarter in quarter_order:
                composite_key = f"{component_id}{var_id}{quarter['quarter_id']}{year_id}{period_id}"
                numeric_value = self._to_float(datacontent.get(composite_key))
                values[quarter["quarter_key"]] = numeric_value
                displays[quarter["quarter_key"]] = self._format_decimal(numeric_value)

            row = {
                "label": component_label,
                "values": values,
                "displays": displays,
                "total_value": values.get("total"),
                "total_display": displays.get("total", "—"),
            }

            if component_label == "Produk Domestik Regional Bruto":
                pdrb_total_row = row
                continue

            component_rows.append(row)

        component_rows = [row for row in component_rows if row.get("total_value") is not None]
        component_rows.sort(key=lambda item: item.get("total_value") or 0, reverse=True)

        quarter_series = [
            {
                "quarter_key": quarter["quarter_key"],
                "label": quarter["label"],
                "value": (pdrb_total_row.get("values") or {}).get(quarter["quarter_key"]),
                "display_value": (pdrb_total_row.get("displays") or {}).get(quarter["quarter_key"], "—"),
            }
            for quarter in quarter_order
        ]

        annual_total_display = (pdrb_total_row.get("displays") or {}).get("total", "—")
        annual_total_value = (pdrb_total_row.get("values") or {}).get("total")

        return {
            "key": definition.key,
            "title": definition.title,
            "subtitle": definition.subtitle,
            "available": bool(component_rows and quarter_series),
            "year": year,
            "unit": self._strip_html(var_items[0].get("unit")) or "Miliar Rupiah",
            "updated_at": str(payload.get("last_update") or "").strip(),
            "source": self._strip_html(var_items[0].get("note")) or "Web API BPS",
            "annual_total_value": annual_total_value,
            "annual_total_display": annual_total_display,
            "top_components": component_rows[:_PDRB_PENGELUARAN_TOP_LIMIT],
            "component_rows": component_rows,
            "quarter_series": quarter_series,
        }

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
    def _extract_latest_change(change_log: list[dict[str, Any]]) -> str:
        if not change_log:
            return ""
        return OfficialStatisticsService._strip_html(change_log[0].get("perubahan"))

    @staticmethod
    def _split_sector_label(label: str) -> tuple[str, str]:
        match = re.match(r"^([A-Z](?:,[A-Z])*)\s+(.+)$", label)
        if not match:
            return "", label
        return match.group(1), match.group(2)

    @staticmethod
    def _clean_label(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip())

    @staticmethod
    def _strip_html(value: Any) -> str:
        raw = html.unescape(str(value or "")).replace("<br>", " ").replace("<br/>", " ")
        clean = re.sub(r"<[^>]+>", " ", raw)
        return re.sub(r"\s+", " ", clean).strip(" -\n\t")

    @staticmethod
    def _parse_localized_number(value: str) -> float | None:
        text = str(value or "").strip()
        if not text:
            return None
        normalized = text.replace(".", "").replace(",", ".")
        try:
            return float(normalized)
        except ValueError:
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
