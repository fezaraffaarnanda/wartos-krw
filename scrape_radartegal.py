"""
Scraper berita lokal RadarTegal (Playwright)
Sumber: https://radartegal.disway.id/kategori/lokal

Paginasi: berbasis offset  /kategori/lokal/30  /60  ... (30 artikel per halaman)
Output:   radartegal_lokal.csv  (title, date, url, content, tags)

Cara pakai:
    python scrape_radartegal.py                        # scrape semua halaman
    python scrape_radartegal.py --start-page 1 --end-page 10
    python scrape_radartegal.py --headless false       # tampilkan browser
    python scrape_radartegal.py --delay 2.0            # jeda antar request (detik)
"""

import argparse
import asyncio
import csv
import random
import re
import signal
import time
from pathlib import Path

from playwright.async_api import async_playwright, Page, TimeoutError as PwTimeout


# ── Konstanta ──────────────────────────────────────────────────────────────────

BASE_URL       = "https://radartegal.disway.id"
LISTING_URL    = f"{BASE_URL}/kategori/lokal"
OUTPUT_FILE    = "radartegal_lokal_new.csv"
CSV_FIELDNAMES = ["title", "date", "url", "content", "tags"]

PAGE_SIZE    = 30       # jumlah artikel per halaman listing
MAX_RETRIES  = 3        # maksimal percobaan ulang per request
BASE_DELAY   = 1.5      # jeda dasar antar request (detik)
GOTO_TIMEOUT = 30_000   # timeout page.goto() dalam milidetik


# ── Pembantu paginasi ──────────────────────────────────────────────────────────

def listing_url_for_page(page_num: int) -> str:
    """Kembalikan URL halaman listing berdasarkan nomor halaman (mulai dari 1)."""
    if page_num == 1:
        return LISTING_URL
    offset = (page_num - 1) * PAGE_SIZE
    return f"{LISTING_URL}/{offset}"


async def get_max_listing_page(page: Page) -> int:
    """
    Baca paginasi halaman listing dan kembalikan nomor halaman terakhir.
    Situs menggunakan atribut data-ci-pagination-page; link 'Last' menyimpan nilai maks.
    """
    try:
        links = await page.query_selector_all("ul.pagination li a[data-ci-pagination-page]")
        max_page = 1
        for link in links:
            val = await link.get_attribute("data-ci-pagination-page")
            if val and val.isdigit():
                n = int(val)
                if n > max_page:
                    max_page = n
        return max_page
    except Exception as exc:
        print(f"[PERINGATAN] Tidak dapat menentukan jumlah halaman: {exc}")
        return 1


# ── Wrapper retry ──────────────────────────────────────────────────────────────

async def goto_with_retry(
    page: Page,
    url: str,
    delay: float,
    retries: int = MAX_RETRIES,
) -> bool:
    """Buka URL dengan percobaan ulang dan backoff. Kembalikan True jika berhasil."""
    for attempt in range(1, retries + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT)
            await asyncio.sleep(delay + random.uniform(0, 0.8))
            return True
        except PwTimeout:
            wait = BASE_DELAY * (2 ** attempt)
            print(f"  [COBA {attempt}/{retries}] Timeout: {url} — tunggu {wait:.1f}s")
            await asyncio.sleep(wait)
        except Exception as exc:
            wait = BASE_DELAY * (2 ** attempt)
            print(f"  [COBA {attempt}/{retries}] Error: {exc} — tunggu {wait:.1f}s")
            await asyncio.sleep(wait)
    return False


# ── Scraping halaman listing ───────────────────────────────────────────────────

async def scrape_listing_page(page: Page, url: str, delay: float) -> list[tuple[str, str]]:
    """
    Buka halaman listing dan kembalikan daftar (judul, url_artikel).
    Hanya mengambil h2.media-heading (bukan h4 di sidebar).
    """
    print(f"  Membuka halaman listing: {url}")
    ok = await goto_with_retry(page, url, delay)
    if not ok:
        print(f"  [LEWATI] Gagal membuka halaman listing: {url}")
        return []

    articles: list[tuple[str, str]] = []
    headings = await page.query_selector_all("h2.media-heading a")
    for a_tag in headings:
        title = (await a_tag.inner_text()).strip()
        href  = await a_tag.get_attribute("href") or ""
        if href.startswith("/"):
            href = BASE_URL + href
        if title and href:
            articles.append((title, href))

    return articles


# ── Pembersih konten ───────────────────────────────────────────────────────────

# Awalan baris yang merupakan boilerplate dan harus dihapus
_BOILERPLATE_PREFIXES = (
    "BACA JUGA",                                     # tautan artikel terkait
    "Cek Berita dan Artikel lainnya di Google News",  # footer Google News
    "Sumber:",                                        # label sumber tanpa isi
)

def clean_content(text: str) -> str:
    """
    Bersihkan konten artikel dari teks sampah:
      - Baris yang diawali "BACA JUGA"
      - Baris footer Google News
      - Baris "Sumber:" yang kosong
      - Baris pemisah "--" yang berdiri sendiri
      - Trailing "--" pada baris caption foto
    """
    cleaned: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()

        # Hapus baris boilerplate
        if any(line.startswith(prefix) for prefix in _BOILERPLATE_PREFIXES):
            continue

        # Hapus pemisah double-dash
        if line == "--":
            continue

        # Potong trailing "--" pada caption foto, teks caption tetap disimpan
        line = re.sub(r"\s*--$", "", line).strip()

        if line:
            cleaned.append(line)

    return "\n".join(cleaned)


# ── Scraping artikel ───────────────────────────────────────────────────────────

async def extract_article_content(page: Page) -> tuple[str, str, str]:
    """
    Ekstrak data dari halaman artikel yang sedang dibuka:
      - Tanggal: dari span.date
      - Isi: dari tag p dalam div.post.text-black-1
      - Tag: dari a[href*='/listtag/'] dalam ul.list-inline
    Kembalikan (tanggal, isi_bersih, tag_str).
    Tag dipisahkan dengan " | ".
    """
    # Tanggal
    date_el  = await page.query_selector("span.date")
    date_str = (await date_el.inner_text()).strip() if date_el else ""

    # Isi artikel
    content_div = await page.query_selector("div.post.text-black-1")
    parts: list[str] = []
    if content_div:
        paragraphs = await content_div.query_selector_all("p")
        for p in paragraphs:
            text = (await p.inner_text()).strip()
            if text:
                parts.append(text)

    # Tag artikel
    tag_links = await page.query_selector_all("ul.list-inline li a[href*='/listtag/']")
    tag_list: list[str] = []
    for a in tag_links:
        tag = (await a.inner_text()).strip().lstrip("#").strip()
        if tag:
            tag_list.append(tag)
    tags_str = " | ".join(tag_list)

    return date_str, clean_content("\n".join(parts)), tags_str


async def scrape_article(
    page: Page,
    url: str,
    delay: float,
) -> tuple[str, str, str]:
    """
    Buka halaman artikel, ekstrak tanggal, isi, dan tag.
    Jika artikel memiliki paginasi internal (ul.pagination), ikuti semua halamannya.
    Tag hanya diambil dari halaman pertama.
    Kembalikan (tanggal, isi_lengkap, tag_str).
    """
    ok = await goto_with_retry(page, url, delay)
    if not ok:
        return "", f"ERROR: gagal membuka {url}", ""

    date_str, body, tags_str = await extract_article_content(page)
    all_parts = [body] if body else []

    # Tangani paginasi internal artikel
    visited: set[str] = {url}
    pagination_links = await page.query_selector_all("ul.pagination li a[data-ci-pagination-page]")
    extra_urls: list[str] = []
    for link in pagination_links:
        href = await link.get_attribute("href") or ""
        if href.startswith("/"):
            href = BASE_URL + href
        if href and href not in visited:
            extra_urls.append(href)
            visited.add(href)

    for extra_url in extra_urls:
        print(f"    -> halaman lanjutan artikel: {extra_url}")
        ok2 = await goto_with_retry(page, extra_url, delay)
        if ok2:
            _, sub_body, _ = await extract_article_content(page)
            if sub_body:
                all_parts.append(sub_body)

    return date_str, "\n\n".join(all_parts), tags_str


# ── Pembantu CSV ───────────────────────────────────────────────────────────────

def load_scraped_urls(output_file: str) -> set[str]:
    """Baca CSV yang sudah ada dan kembalikan kumpulan URL yang sudah di-scrape."""
    scraped: set[str] = set()
    if not Path(output_file).exists():
        return scraped
    try:
        with open(output_file, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("url"):
                    scraped.add(row["url"])
        print(f"[LANJUT] {len(scraped)} artikel sudah di-scrape sebelumnya, dilewati.")
    except Exception as exc:
        print(f"[PERINGATAN] Tidak bisa membaca CSV lama: {exc}")
    return scraped


def open_csv_writer(output_file: str, append: bool):
    """Buka file CSV untuk ditulis atau dilanjutkan. Kembalikan (file_handle, writer)."""
    mode     = "a" if append else "w"
    need_hdr = not Path(output_file).exists() or not append
    fh       = open(output_file, mode, newline="", encoding="utf-8-sig")
    writer   = csv.DictWriter(fh, fieldnames=CSV_FIELDNAMES)
    if need_hdr:
        writer.writeheader()
    return fh, writer


# ── Penanganan sinyal ──────────────────────────────────────────────────────────

_shutdown_requested = False

def _handle_sigint(sig, frame):
    global _shutdown_requested
    _shutdown_requested = True
    print("\n[BERHENTI] Ctrl+C diterima. Menyelesaikan artikel saat ini lalu berhenti.\n")


# ── Orkestrator utama ──────────────────────────────────────────────────────────

async def run(
    start_page: int,
    end_page: int | None,
    headless: bool,
    delay: float,
):
    global _shutdown_requested

    scraped_urls = load_scraped_urls(OUTPUT_FILE)
    append_mode  = len(scraped_urls) > 0
    fh, writer   = open_csv_writer(OUTPUT_FILE, append=append_mode)

    total_written = 0
    start_time    = time.time()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        try:
            # Langkah 1: deteksi total halaman listing
            print("Membuka halaman listing pertama untuk deteksi paginasi...")
            ok = await goto_with_retry(page, LISTING_URL, delay)
            if not ok:
                print("[ERROR] Tidak bisa membuka halaman listing. Proses dihentikan.")
                return

            max_page = await get_max_listing_page(page)
            effective_end = min(end_page, max_page) if end_page else max_page
            print(f"Total halaman listing: {max_page}")
            print(f"Scraping halaman {start_page} sampai {effective_end}")
            print("=" * 60)

            # Langkah 2: iterasi setiap halaman listing
            for page_num in range(start_page, effective_end + 1):
                if _shutdown_requested:
                    break

                listing_url = listing_url_for_page(page_num)
                print(f"\n[Hal. {page_num}/{effective_end}] {listing_url}")

                articles = await scrape_listing_page(page, listing_url, delay)
                print(f"  Ditemukan {len(articles)} artikel.")

                # Langkah 3: scrape setiap artikel
                for idx, (title, article_url) in enumerate(articles, 1):
                    if _shutdown_requested:
                        break

                    if article_url in scraped_urls:
                        print(f"  [{idx}/{len(articles)}] Dilewati (sudah ada): {title[:55]}")
                        continue

                    print(f"  [{idx}/{len(articles)}] {title[:65]}")
                    try:
                        date_str, content, tags_str = await scrape_article(page, article_url, delay)
                        writer.writerow({
                            "title":   title,
                            "date":    date_str,
                            "url":     article_url,
                            "content": content,
                            "tags":    tags_str,
                        })
                        fh.flush()
                        scraped_urls.add(article_url)
                        total_written += 1
                        tag_display = tags_str[:45] + "..." if len(tags_str) > 45 else tags_str
                        print(f"    Selesai | {date_str[:28]} | {len(content)} karakter | {tag_display}")
                    except Exception as exc:
                        print(f"    [ERROR] {exc}")
                        writer.writerow({
                            "title":   title,
                            "date":    "",
                            "url":     article_url,
                            "content": f"ERROR: {exc}",
                            "tags":    "",
                        })
                        fh.flush()
                        total_written += 1

        finally:
            await browser.close()
            fh.close()

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"Selesai. {total_written} artikel ditulis ke {OUTPUT_FILE}")
    print(f"Durasi: {elapsed / 60:.1f} menit")
    print("=" * 60)


# ── API untuk dipanggil dari Flask ──────────────────────────────────────────────

async def scrape_new_articles(
    existing_urls: set[str],
    headless: bool = True,
    delay: float = BASE_DELAY,
    max_pages: int | None = None,
    on_progress=None,
) -> list[dict]:
    """
    Scrape berita baru mulai dari halaman 1 (terbaru).
    Berhenti begitu menemukan URL yang sudah ada di existing_urls.
    max_pages: batas jumlah halaman listing (None = semua).
    on_progress(msg): callback opsional untuk kirim pesan progress.
    Kembalikan list dict {title, date, url, content, tags}.
    """
    new_articles: list[dict] = []

    def log(msg: str):
        print(msg)
        if on_progress:
            on_progress(msg)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        try:
            log("Membuka halaman listing untuk deteksi paginasi...")
            ok = await goto_with_retry(page, LISTING_URL, delay)
            if not ok:
                log("[ERROR] Gagal membuka halaman listing.")
                return new_articles

            max_page = await get_max_listing_page(page)
            if max_pages is not None:
                max_page = min(max_page, max_pages)
            log(f"Total halaman listing: {max_page}")

            stop = False
            for page_num in range(1, max_page + 1):
                if stop:
                    break

                listing_url = listing_url_for_page(page_num)
                log(f"[Hal. {page_num}] {listing_url}")

                articles = await scrape_listing_page(page, listing_url, delay)
                log(f"  Ditemukan {len(articles)} artikel.")

                for idx, (title, article_url) in enumerate(articles, 1):
                    if article_url in existing_urls:
                        log(f"  [{idx}/{len(articles)}] Duplikat ditemukan, berhenti: {title[:55]}")
                        stop = True
                        break

                    log(f"  [{idx}/{len(articles)}] Scraping: {title[:60]}")
                    try:
                        date_str, content, tags_str = await scrape_article(page, article_url, delay)
                        new_articles.append({
                            "title":   title,
                            "date":    date_str,
                            "url":     article_url,
                            "content": content,
                            "tags":    tags_str,
                        })
                        existing_urls.add(article_url)
                        log(f"    Selesai | {date_str[:28]} | {len(content)} karakter")
                    except Exception as exc:
                        log(f"    [ERROR] {exc}")

        finally:
            await browser.close()

    log(f"Total berita baru: {len(new_articles)}")
    return new_articles


# ── Entry point ────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scraper berita lokal radartegal.disway.id/kategori/lokal"
    )
    parser.add_argument(
        "--start-page", type=int, default=1, metavar="N",
        help="Halaman listing awal (default: 1)",
    )
    parser.add_argument(
        "--end-page", type=int, default=None, metavar="N",
        help="Halaman listing akhir inklusif (default: halaman terakhir)",
    )
    parser.add_argument(
        "--headless", type=lambda v: v.lower() != "false", default=True,
        metavar="true|false",
        help="Jalankan browser tanpa tampilan (default: true)",
    )
    parser.add_argument(
        "--delay", type=float, default=BASE_DELAY, metavar="DETIK",
        help=f"Jeda dasar antar request dalam detik (default: {BASE_DELAY})",
    )
    parser.add_argument(
        "--output", type=str, default=OUTPUT_FILE, metavar="FILE",
        help=f"Path file CSV output (default: {OUTPUT_FILE})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _handle_sigint)

    args = parse_args()
    OUTPUT_FILE = args.output

    print("=" * 60)
    print("Scraper Berita Lokal RadarTegal")
    print("=" * 60)
    print(f"  Output   : {OUTPUT_FILE}")
    print(f"  Headless : {args.headless}")
    print(f"  Jeda     : {args.delay}s")
    print(f"  Halaman  : {args.start_page} sampai {args.end_page or 'terakhir'}")
    print()

    asyncio.run(
        run(
            start_page=args.start_page,
            end_page=args.end_page,
            headless=args.headless,
            delay=args.delay,
        )
    )
