"""Client Web API BPS untuk statistik resmi wilayah fokus (lihat config/region.py)."""

from __future__ import annotations

import json
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config.region import APP_NAME, BPS_DOMAIN_ID, BPS_PDRB_WILAYAH_ID
from config.settings import get_settings

_BPS_BASE_URL = "https://webapi.bps.go.id/v1/api"
_USER_AGENT = f"Mozilla/5.0 (compatible; {APP_NAME}-BPS/1.0)"
_PDRB_SOURCE_ID = 25
_PDRB_ADHK_TABLE_ID = "UklLSnFZZnMzMlJiSWpMOExJODIrQT09"
_PDRB_ADHB_TABLE_ID = "S1RMUWRYb0NWc0Y5L05QQkxzcWw3Zz09"
_TPT_TPAK_VAR_ID = 420
_KEMISKINAN_VAR_ID = 944
_PDRB_PENGELUARAN_ADHB_VAR_ID = 962
_PDRB_PENGELUARAN_ADHK_VAR_ID = 963
_DOMAIN_ID = BPS_DOMAIN_ID
_PDRB_WILAYAH_ID = BPS_PDRB_WILAYAH_ID


class BPSWebApiClient:
    """Client sederhana untuk endpoint statistik resmi BPS."""

    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        self._api_key = str(api_key or settings.BPS_API_KEY or "").strip()
        self._ssl_fallback_logged = False

    def fetch_pdrb_adhk(self, year: int) -> dict[str, Any]:
        return self._request_json(self._build_pdrb_url(year, _PDRB_ADHK_TABLE_ID))

    def fetch_pdrb_adhb(self, year: int) -> dict[str, Any]:
        return self._request_json(self._build_pdrb_url(year, _PDRB_ADHB_TABLE_ID))

    def fetch_tpt_tpak(self, year: int) -> dict[str, Any]:
        return self._request_json(self._build_dynamic_url(_TPT_TPAK_VAR_ID, year))

    def fetch_kemiskinan(self, year: int) -> dict[str, Any]:
        return self._request_json(self._build_dynamic_url(_KEMISKINAN_VAR_ID, year))

    def fetch_pdrb_pengeluaran_adhb(self, year: int) -> dict[str, Any]:
        return self._request_json(self._build_dynamic_url(_PDRB_PENGELUARAN_ADHB_VAR_ID, year))

    def fetch_pdrb_pengeluaran_adhk(self, year: int) -> dict[str, Any]:
        return self._request_json(self._build_dynamic_url(_PDRB_PENGELUARAN_ADHK_VAR_ID, year))

    def _build_pdrb_url(self, year: int, table_id: str) -> str:
        return (
            f"{_BPS_BASE_URL}/interoperabilitas/datasource/simdasi/"
            f"id/{_PDRB_SOURCE_ID}/tahun/{year}/id_tabel/{table_id}/"
            f"wilayah/{_PDRB_WILAYAH_ID}/key/{self._api_key}"
        )

    def _build_dynamic_url(self, var_id: int, year: int) -> str:
        year_id = self._to_bps_year_id(year)
        return (
            f"{_BPS_BASE_URL}/list/model/data/lang/ind/domain/{_DOMAIN_ID}/"
            f"var/{var_id}/th/{year_id}/key/{self._api_key}"
        )

    @staticmethod
    def _to_bps_year_id(year: int) -> int:
        return int(year) - 1900

    def _request_json(self, url: str) -> dict[str, Any]:
        if not self._api_key:
            raise RuntimeError("BPS_API_KEY belum dikonfigurasi.")

        request = Request(url, headers={"User-Agent": _USER_AGENT})

        try:
            return self._load_json(request, ssl.create_default_context())
        except (ssl.SSLCertVerificationError, ssl.SSLError):
            if not self._ssl_fallback_logged:
                print("[BPS API] Sertifikat SSL gagal diverifikasi, mencoba fallback koneksi.")
                self._ssl_fallback_logged = True
            return self._load_json(request, ssl._create_unverified_context())

    @staticmethod
    def _load_json(request: Request, ssl_context: ssl.SSLContext) -> dict[str, Any]:
        try:
            with urlopen(request, timeout=30, context=ssl_context) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {exc.code} dari Web API BPS: {detail}") from exc
        except URLError as exc:
            if isinstance(exc.reason, (ssl.SSLCertVerificationError, ssl.SSLError)):
                raise exc.reason
            raise RuntimeError(f"Gagal terhubung ke Web API BPS: {exc.reason}") from exc

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Respons Web API BPS tidak valid.") from exc

        if not isinstance(payload, dict):
            raise RuntimeError("Format respons Web API BPS tidak dikenali.")

        return payload
