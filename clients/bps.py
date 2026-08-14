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
_TPT_TPAK_VAR_ID = 420
_KEMISKINAN_VAR_ID = 944

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

    def fetch_tpt_tpak(self, year: int) -> dict[str, Any]:
        return self._request_json(self._build_dynamic_url(_TPT_TPAK_VAR_ID, year))

    def fetch_kemiskinan(self, year: int) -> dict[str, Any]:
        return self._request_json(self._build_dynamic_url(_KEMISKINAN_VAR_ID, year))

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
