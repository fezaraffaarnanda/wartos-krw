"""Service statistik resmi BPS untuk dashboard dan konteks AI."""

from __future__ import annotations

import html
import re
import time
from threading import Lock
from typing import Any

from clients.bps import BPSWebApiClient

_PAGE_SUPPORTED_YEARS = (2025, 2024)
_DEFAULT_PAGE_YEAR = _PAGE_SUPPORTED_YEARS[0]
_CACHE_TTL_SECONDS = 30 * 60
_PDRB_TOP_LIMIT = 8
_AI_TOPIC_DEFAULTS = ("pdrb", "kemiskinan", "pengangguran")

_CACHE_LOCK = Lock()
_YEAR_CACHE: dict[int, dict[str, Any]] = {}


class OfficialStatisticsService:
    """Orkestrasi pengambilan dan normalisasi statistik resmi BPS."""

    def __init__(self, bps_client: BPSWebApiClient | None = None):
        self._client = bps_client or BPSWebApiClient()

    def get_dashboard_payload(self, year: int | None = None, force_refresh: bool = False) -> dict[str, Any]:
        selected_year = self._normalize_page_year(year)
        datasets = self.fetch_statistics_bundle(selected_year, force_refresh=force_refresh)
        available_count = sum(1 for dataset in datasets.values() if dataset.get("available"))

        return {
            "status": "ok",
            "year": selected_year,
            "supported_years": list(_PAGE_SUPPORTED_YEARS),
            "available_count": available_count,
            "datasets": datasets,
            "generated_at": int(time.time()),
        }

    def fetch_statistics_bundle(self, year: int, force_refresh: bool = False) -> dict[str, Any]:
        normalized_year = int(year)
        cache_key = normalized_year

        if not force_refresh:
            cached = self._read_cache(cache_key)
            if cached is not None:
                return cached

        datasets = {
            "pdrb_adhk": self._safe_normalize(
                lambda: self._normalize_pdrb_payload(
                    self._client.fetch_pdrb_adhk(normalized_year),
                    dataset_key="pdrb_adhk",
                    dataset_title="PDRB ADHK Lapangan Usaha",
                    dataset_subtitle="Atas Dasar Harga Konstan 2010",
                ),
                dataset_key="pdrb_adhk",
                dataset_title="PDRB ADHK Lapangan Usaha",
                year=normalized_year,
            ),
            "pdrb_adhb": self._safe_normalize(
                lambda: self._normalize_pdrb_payload(
                    self._client.fetch_pdrb_adhb(normalized_year),
                    dataset_key="pdrb_adhb",
                    dataset_title="PDRB ADHB Lapangan Usaha",
                    dataset_subtitle="Atas Dasar Harga Berlaku",
                ),
                dataset_key="pdrb_adhb",
                dataset_title="PDRB ADHB Lapangan Usaha",
                year=normalized_year,
            ),
            "tpt_tpak": self._safe_normalize(
                lambda: self._normalize_tpt_tpak_payload(
                    self._client.fetch_tpt_tpak(normalized_year),
                    year=normalized_year,
                ),
                dataset_key="tpt_tpak",
                dataset_title="TPT dan TPAK",
                year=normalized_year,
            ),
            "kemiskinan": self._safe_normalize(
                lambda: self._normalize_kemiskinan_payload(
                    self._client.fetch_kemiskinan(normalized_year),
                    year=normalized_year,
                ),
                dataset_key="kemiskinan",
                dataset_title="Kemiskinan",
                year=normalized_year,
            ),
        }

        self._write_cache(cache_key, datasets)
        return datasets

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

        if any(keyword in text for keyword in ("pdrb", "adhk", "adhb", "lapangan usaha", "pertumbuhan ekonomi", "sektor")):
            topics.add("pdrb")
        if any(keyword in text for keyword in ("kemiskinan", "miskin", "garis kemiskinan", "bansos", "kesejahteraan")):
            topics.add("kemiskinan")
        if any(keyword in text for keyword in ("pengangguran", "tpt", "tpak", "angkatan kerja", "tenaga kerja", "phk", "lowongan kerja")):
            topics.add("pengangguran")

        if topics:
            return topics

        if any(keyword in text for keyword in ("statistik resmi", "data resmi", "bps", "kondisi ekonomi", "ekonomi tegal")):
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

        deduped: list[int] = []
        seen: set[int] = set()
        for year in candidates:
            if year in seen:
                continue
            deduped.append(year)
            seen.add(year)
        return deduped

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
        adhk = datasets.get("pdrb_adhk") or {}
        adhb = datasets.get("pdrb_adhb") or {}
        if not adhk.get("available") and not adhb.get("available"):
            return ""

        parts = [f"Statistik resmi BPS tahun {year} untuk PDRB Kabupaten Tegal:"]

        if adhk.get("available"):
            top = ", ".join(
                f"{row['label']} ({row['display_value']})" for row in adhk.get("top_rows", [])[:3]
            )
            parts.append(
                f"- PDRB ADHK total {adhk.get('total_display', '—')} miliar rupiah; sektor terbesar: {top}."
            )

        if adhb.get("available"):
            top = ", ".join(
                f"{row['label']} ({row['display_value']})" for row in adhb.get("top_rows", [])[:3]
            )
            parts.append(
                f"- PDRB ADHB total {adhb.get('total_display', '—')} miliar rupiah; sektor terbesar: {top}."
            )

        parts.append(
            "Gunakan statistik resmi ini sebagai pembanding struktural; marker sitasi berita hanya wajib untuk fakta yang berasal dari berita."
        )
        return "\n".join(parts)

    def _build_tpt_ai_block(self, datasets: dict[str, Any], year: int) -> str:
        dataset = datasets.get("tpt_tpak") or {}
        if not dataset.get("available"):
            return ""

        tpak = dataset.get("indicators", {}).get("tpak", {})
        tpt = dataset.get("indicators", {}).get("tpt", {})

        return "\n".join(
            [
                f"Statistik resmi BPS tahun {year} untuk ketenagakerjaan Kabupaten Tegal:",
                (
                    f"- TPAK total {tpak.get('total_display', '—')} persen; "
                    f"laki-laki {tpak.get('male_display', '—')} persen; "
                    f"perempuan {tpak.get('female_display', '—')} persen."
                ),
                (
                    f"- TPT total {tpt.get('total_display', '—')} persen; "
                    f"laki-laki {tpt.get('male_display', '—')} persen; "
                    f"perempuan {tpt.get('female_display', '—')} persen."
                ),
                "Gunakan statistik resmi ini sebagai baseline; marker sitasi berita hanya untuk fakta dari berita.",
            ]
        )

    def _build_kemiskinan_ai_block(self, datasets: dict[str, Any], year: int) -> str:
        dataset = datasets.get("kemiskinan") or {}
        if not dataset.get("available"):
            return ""

        tegal = dataset.get("tegal_metrics", {})
        leader = dataset.get("highest_poverty_area", {})

        parts = [f"Statistik resmi BPS tahun {year} untuk kemiskinan Kabupaten Tegal:"]
        parts.append(
            (
                f"- Kabupaten Tegal: garis kemiskinan {tegal.get('poverty_line_display', '—')} rupiah/kapita/bulan, "
                f"jumlah penduduk miskin {tegal.get('poor_population_display', '—')} ribu jiwa, "
                f"persentase penduduk miskin {tegal.get('poverty_rate_display', '—')} persen."
            )
        )
        if leader:
            parts.append(
                f"- Persentase kemiskinan tertinggi di Eks Karesidenan Pekalongan berada di {leader.get('label', '—')} ({leader.get('display_value', '—')} persen)."
            )
        parts.append("Gunakan statistik resmi ini sebagai acuan utama; marker sitasi berita hanya untuk fakta dari berita.")
        return "\n".join(parts)

    def _normalize_page_year(self, year: int | None) -> int:
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

    def _safe_normalize(
        self,
        builder,
        *,
        dataset_key: str,
        dataset_title: str,
        year: int,
    ) -> dict[str, Any]:
        try:
            return builder()
        except Exception as exc:
            print(f"[BPS] Gagal memuat {dataset_key} tahun {year}: {exc}")
            return self._unavailable_dataset(dataset_key, dataset_title, year, str(exc))

    def _normalize_pdrb_payload(
        self,
        payload: dict[str, Any],
        *,
        dataset_key: str,
        dataset_title: str,
        dataset_subtitle: str,
    ) -> dict[str, Any]:
        if payload.get("status") != "OK":
            return self._unavailable_dataset(dataset_key, dataset_title, 0, payload.get("message", "Data tidak tersedia."))

        container = payload.get("data") or []
        if len(container) < 2 or not isinstance(container[1], dict):
            return self._unavailable_dataset(dataset_key, dataset_title, 0, "Struktur data PDRB tidak dikenali.")

        content = container[1]
        data_rows = content.get("data") or []
        column_map = content.get("kolom") or {}
        column_key = next(iter(column_map.keys()), "")
        if not data_rows or not column_key:
            return self._unavailable_dataset(dataset_key, dataset_title, int(content.get("tahun_data") or 0), "Tidak ada data tabel untuk tahun ini.")

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
                    "value_code": str(value_info.get("value_code") or "").strip(),
                }
            )

        rows.sort(key=lambda item: item["value"], reverse=True)
        year = int(content.get("tahun_data") or 0)

        latest_change = ""
        change_log = content.get("change_log") or []
        if change_log:
            latest_change = self._strip_html(change_log[0].get("perubahan"))

        note_map = content.get("keterangan_data") or {}
        value_note = note_map.get(total_code, "") if total_code else ""

        return {
            "key": dataset_key,
            "title": dataset_title,
            "subtitle": dataset_subtitle,
            "available": bool(rows),
            "year": year,
            "unit": "Miliar rupiah",
            "updated_at": str(content.get("table_updated") or content.get("created") or "").strip(),
            "source": self._strip_html(content.get("sumber")) or "Web API BPS",
            "latest_change": latest_change,
            "value_note": self._strip_html(value_note),
            "table_note": self._strip_html(content.get("catatan")),
            "total_label": "Produk Domestik Bruto",
            "total_display": total_display,
            "total_value": total_value,
            "top_rows": rows[:_PDRB_TOP_LIMIT],
            "rows": rows,
        }

    def _normalize_tpt_tpak_payload(self, payload: dict[str, Any], *, year: int) -> dict[str, Any]:
        if payload.get("status") != "OK":
            return self._unavailable_dataset("tpt_tpak", "TPT dan TPAK", year, payload.get("message", "Data tidak tersedia."))

        var_items = payload.get("var") or []
        turvar_items = payload.get("turvar") or []
        vervar_items = payload.get("vervar") or []
        tahun_items = payload.get("tahun") or []
        turtahun_items = payload.get("turtahun") or []
        datacontent = payload.get("datacontent") or {}

        if not var_items or not turvar_items or not vervar_items or not tahun_items or not datacontent:
            return self._unavailable_dataset("tpt_tpak", "TPT dan TPAK", year, "Tidak ada data TPT/TPAK untuk tahun ini.")

        var_id = str(var_items[0].get("val"))
        year_id = str(tahun_items[0].get("val"))
        period_id = str((turtahun_items[0] if turtahun_items else {}).get("val", 0))

        gender_map = {str(item.get("val")): str(item.get("label") or "") for item in turvar_items}
        indicator_map = {str(item.get("val")): str(item.get("label") or "") for item in vervar_items}

        indicators: dict[str, Any] = {}
        chart_groups: list[dict[str, Any]] = []

        for indicator_id, indicator_label in indicator_map.items():
            slug = "tpak" if "TPAK" in indicator_label else "tpt"
            values_by_gender: dict[str, Any] = {}

            for gender_id, gender_label in gender_map.items():
                composite_key = f"{indicator_id}{var_id}{gender_id}{year_id}{period_id}"
                numeric_value = self._to_float(datacontent.get(composite_key))
                values_by_gender[gender_label] = numeric_value
                chart_groups.append(
                    {
                        "indicator": indicator_label,
                        "indicator_key": slug,
                        "gender": gender_label,
                        "value": numeric_value,
                    }
                )

            indicators[slug] = {
                "label": indicator_label,
                "male": values_by_gender.get("Laki-laki"),
                "female": values_by_gender.get("Perempuan"),
                "total": values_by_gender.get("Jumlah"),
                "male_display": self._format_decimal(values_by_gender.get("Laki-laki")),
                "female_display": self._format_decimal(values_by_gender.get("Perempuan")),
                "total_display": self._format_decimal(values_by_gender.get("Jumlah")),
            }

        return {
            "key": "tpt_tpak",
            "title": "TPT dan TPAK",
            "subtitle": "Perbandingan menurut jenis kelamin",
            "available": bool(indicators),
            "year": year,
            "unit": "Persen",
            "updated_at": str(payload.get("last_update") or "").strip(),
            "source": self._strip_html(var_items[0].get("note")) or "Web API BPS",
            "indicators": indicators,
            "chart_groups": chart_groups,
        }

    def _normalize_kemiskinan_payload(self, payload: dict[str, Any], *, year: int) -> dict[str, Any]:
        if payload.get("status") != "OK":
            return self._unavailable_dataset("kemiskinan", "Kemiskinan", year, payload.get("message", "Data tidak tersedia."))

        var_items = payload.get("var") or []
        turvar_items = payload.get("turvar") or []
        vervar_items = payload.get("vervar") or []
        tahun_items = payload.get("tahun") or []
        turtahun_items = payload.get("turtahun") or []
        datacontent = payload.get("datacontent") or {}

        if not var_items or not turvar_items or not vervar_items or not tahun_items or not datacontent:
            return self._unavailable_dataset("kemiskinan", "Kemiskinan", year, "Tidak ada data kemiskinan untuk tahun ini.")

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

            if any(row.get(key) is not None for key in ("poverty_line", "poor_population", "poverty_rate")):
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
            "key": "kemiskinan",
            "title": "Kemiskinan",
            "subtitle": "Eks Karesidenan Pekalongan",
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

    @staticmethod
    def _unavailable_dataset(dataset_key: str, dataset_title: str, year: int, message: str) -> dict[str, Any]:
        return {
            "key": dataset_key,
            "title": dataset_title,
            "available": False,
            "year": year,
            "message": message or "Data tidak tersedia untuk tahun ini.",
            "rows": [],
            "top_rows": [],
        }

    @staticmethod
    def _read_cache(year: int) -> dict[str, Any] | None:
        with _CACHE_LOCK:
            cached = _YEAR_CACHE.get(year)
            if not cached:
                return None
            if time.time() - cached["ts"] > _CACHE_TTL_SECONDS:
                _YEAR_CACHE.pop(year, None)
                return None
            return cached["value"]

    @staticmethod
    def _write_cache(year: int, value: dict[str, Any]) -> None:
        with _CACHE_LOCK:
            _YEAR_CACHE[year] = {"ts": time.time(), "value": value}

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
