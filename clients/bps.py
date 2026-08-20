"""Client Web API BPS untuk statistik resmi wilayah fokus (lihat config/region.py)."""

from __future__ import annotations

import json
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config.region import APP_NAME, BPS_DOMAIN_ID
from config.settings import get_settings

_BPS_BASE_URL = "https://webapi.bps.go.id/v1/api"
_USER_AGENT = f"Mozilla/5.0 (compatible; {APP_NAME}-BPS/1.0)"

# Ketenagakerjaan Kabupaten Karawang. Kedua var hanya punya satu nilai per tahun
# (tanpa rincian gender), jadi yang dipakai adalah serinya, bukan satu titik.
_TPAK_VAR_ID = 571
_TPT_VAR_ID = 570
# Panjang jendela seri yang diminta ke Web API, dihitung mundur dari tahun terpilih.
_LABOR_SERIES_YEARS_BACK = 12

# PDRB triwulanan Kabupaten Karawang. Semua var di bawah memakai endpoint
# dinamis `list/model/data` pada domain yang sama, jadi cukup `_build_dynamic_url`.
_PDRB_LU_ADHB_VAR_ID = 610
_PDRB_LU_ADHK_VAR_ID = 611
_PDRB_LU_DISTRIBUSI_VAR_ID = 612
_PDRB_PENGELUARAN_ADHB_VAR_ID = 617
_PDRB_PENGELUARAN_ADHK_VAR_ID = 618
_PDRB_PENGELUARAN_DISTRIBUSI_VAR_ID = 619

_DOMAIN_ID = BPS_DOMAIN_ID


class BPSWebApiClient:
    """Client sederhana untuk endpoint statistik resmi BPS."""

    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        self._api_key = str(api_key or settings.BPS_API_KEY or "").strip()
        self._ssl_fallback_logged = False

    def fetch_tpak_series(self, year: int) -> dict[str, Any]:
        return self._request_json(self._build_series_url(_TPAK_VAR_ID, year))

    def fetch_tpt_series(self, year: int) -> dict[str, Any]:
        return self._request_json(self._build_series_url(_TPT_VAR_ID, year))

    def fetch_pdrb_lu_adhb(self, year: int) -> dict[str, Any]:
        return self._request_json(self._build_dynamic_url(_PDRB_LU_ADHB_VAR_ID, year))

    def fetch_pdrb_lu_adhk(self, year: int) -> dict[str, Any]:
        return self._request_json(self._build_dynamic_url(_PDRB_LU_ADHK_VAR_ID, year))

    def fetch_pdrb_lu_distribusi(self, year: int) -> dict[str, Any]:
        return self._request_json(self._build_dynamic_url(_PDRB_LU_DISTRIBUSI_VAR_ID, year))

    def fetch_pdrb_pengeluaran_adhb(self, year: int) -> dict[str, Any]:
        return self._request_json(self._build_dynamic_url(_PDRB_PENGELUARAN_ADHB_VAR_ID, year))

    def fetch_pdrb_pengeluaran_adhk(self, year: int) -> dict[str, Any]:
        return self._request_json(self._build_dynamic_url(_PDRB_PENGELUARAN_ADHK_VAR_ID, year))

    def fetch_pdrb_pengeluaran_distribusi(self, year: int) -> dict[str, Any]:
        return self._request_json(self._build_dynamic_url(_PDRB_PENGELUARAN_DISTRIBUSI_VAR_ID, year))

    def _build_series_url(self, var_id: int, year: int) -> str:
        """URL untuk deret tahunan: Web API menerima daftar `th` yang dipisah koma."""
        end_id = self._to_bps_year_id(year)
        start_id = end_id - _LABOR_SERIES_YEARS_BACK
        year_ids = ",".join(str(year_id) for year_id in range(start_id, end_id + 1))
        return (
            f"{_BPS_BASE_URL}/list/model/data/lang/ind/domain/{_DOMAIN_ID}/"
            f"var/{var_id}/th/{year_ids}/key/{self._api_key}"
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
