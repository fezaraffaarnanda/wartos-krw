"""Client Google Sheets untuk tabel statistik yang tidak tersedia di Web API BPS.

Sebagian indikator wilayah fokus tidak dirilis lewat `webapi.bps.go.id` untuk
domain yang dipakai aplikasi ini, jadi angkanya dipelihara manual di spreadsheet
dan dibaca lewat endpoint `gviz` (CSV). Spreadsheet-nya wajib bisa diakses
"siapa saja yang punya link" — endpoint ini tidak mengirim kredensial apa pun.
"""

from __future__ import annotations

import csv
import io
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from config.region import APP_NAME, KEMISKINAN_SHEET_ID, KEMISKINAN_SHEET_NAME

_SHEETS_BASE_URL = "https://docs.google.com/spreadsheets/d"
_USER_AGENT = f"Mozilla/5.0 (compatible; {APP_NAME}-Sheets/1.0)"


class GoogleSheetsClient:
    """Pembaca satu sheet publik sebagai matriks sel mentah."""

    def __init__(self, ssl_context: ssl.SSLContext | None = None):
        self._ssl_context = ssl_context

    def fetch_kemiskinan(self, year: int) -> dict[str, Any]:
        """Ambil sheet kemiskinan.

        `year` diabaikan: sheet memuat seluruh deret tahun sekaligus, dan
        pemotongan sampai tahun terpilih dilakukan di normalizer.
        """
        return self.fetch_sheet(KEMISKINAN_SHEET_ID, KEMISKINAN_SHEET_NAME)

    def fetch_sheet(self, sheet_id: str, sheet_name: str) -> dict[str, Any]:
        url = self._build_csv_url(sheet_id, sheet_name)
        body = self._request_text(url)

        rows = [row for row in csv.reader(io.StringIO(body))]
        if not rows:
            raise RuntimeError("Sheet tidak berisi baris apa pun.")

        return {
            "status": "OK",
            "sheet_id": sheet_id,
            "sheet_name": sheet_name,
            "rows": rows,
        }

    @staticmethod
    def _build_csv_url(sheet_id: str, sheet_name: str) -> str:
        return (
            f"{_SHEETS_BASE_URL}/{quote(sheet_id)}/gviz/tq"
            f"?tqx=out:csv&sheet={quote(sheet_name)}"
        )

    def _request_text(self, url: str) -> str:
        request = Request(url, headers={"User-Agent": _USER_AGENT})
        context = self._ssl_context or ssl.create_default_context()

        try:
            with urlopen(request, timeout=30, context=context) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} dari Google Sheets: {exc.reason}") from exc
        except URLError as exc:
            raise RuntimeError(f"Gagal terhubung ke Google Sheets: {exc.reason}") from exc

        # Sheet yang tidak publik membalas halaman login HTML dengan status 200,
        # bukan error, jadi bentuk responsnya harus diperiksa sendiri.
        if body.lstrip().lower().startswith("<!doctype html") or "<html" in body[:200].lower():
            raise RuntimeError(
                "Google Sheets membalas halaman HTML, bukan CSV. "
                "Pastikan spreadsheet dibagikan ke 'siapa saja yang punya link'."
            )

        return body
