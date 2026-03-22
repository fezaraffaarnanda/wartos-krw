"""
Trigger endpoint scraping manual via CRON_SECRET (Bearer token).

Pemakaian:
    python -m scripts.scraping.trigger_scrape
    python -m scripts.scraping.trigger_scrape --max-articles 200
    python -m scripts.scraping.trigger_scrape --base-url http://127.0.0.1:5000

Catatan:
    - Wajib punya CRON_SECRET di .env atau env shell.
    - Endpoint /api/scrape dengan Bearer token berjalan synchronous,
      jadi script menunggu proses selesai dan langsung menampilkan hasil.
"""

from __future__ import annotations

import argparse
import os
import sys

import requests
from dotenv import load_dotenv


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trigger scraping via endpoint /api/scrape")
    parser.add_argument(
        "--max-articles",
        type=int,
        default=150,
        help="Batas maksimal berita per source (default: 150)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://127.0.0.1:5000",
        help="Base URL aplikasi Flask (default: http://127.0.0.1:5000)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1200,
        help="Timeout request dalam detik (default: 1200)",
    )
    return parser


def main() -> int:
    load_dotenv()
    args = _build_parser().parse_args()

    cron_secret = (os.getenv("CRON_SECRET") or "").strip()
    if not cron_secret:
        print("ERROR: CRON_SECRET tidak ditemukan di environment/.env")
        return 1

    max_articles = max(1, min(int(args.max_articles), 999))
    base_url = args.base_url.rstrip("/")
    url = f"{base_url}/api/scrape"

    headers = {
        "Authorization": f"Bearer {cron_secret}",
        "Content-Type": "application/json",
    }
    payload = {"max_articles": max_articles}

    print(f"[SCRAPE TOOL] Trigger scraping ke: {url}")
    print(f"[SCRAPE TOOL] max_articles: {max_articles}")

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=args.timeout)
    except requests.RequestException as exc:
        print(f"ERROR: Gagal request ke endpoint scrape: {exc}")
        return 1

    try:
        body = response.json()
    except ValueError:
        print(f"ERROR: Response bukan JSON (HTTP {response.status_code})")
        print(response.text[:1000])
        return 1

    if response.status_code >= 400 or body.get("status") != "ok":
        message = body.get("message") or "Terjadi kesalahan saat scraping."
        print(f"ERROR: HTTP {response.status_code} - {message}")
        print(body)
        return 1

    print("[SCRAPE TOOL] Scraping selesai.")
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
