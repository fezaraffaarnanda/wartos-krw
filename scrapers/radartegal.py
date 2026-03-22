"""
Scraper berita lokal RadarTegal (requests + BeautifulSoup)
Sumber: https://radartegal.disway.id/kategori/lokal

Versi tanpa browser — cocok untuk deployment di Vercel atau lingkungan
yang tidak mendukung Playwright.

Paginasi: berbasis offset  /kategori/lokal/30  /60  ... (30 artikel/hal)
Output:   radartegal_bs4.csv  (title, date, url, content, tags)

Cara pakai:
    python -m scrapers.radartegal
    python -m scrapers.radartegal --start-page 1 --end-page 5
    python -m scrapers.radartegal --delay 2.0
"""

import argparse
import csv
import random
import re
import signal
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from utils.tags import clean_tags as _clean_tags

# ── Konstanta ──────────────────────────────────────────────────────────────────

BASE_URL       = "https://radartegal.disway.id"
LISTING_URL    = f"{BASE_URL}/kategori/lokal"
OUTPUT_FILE    = "radartegal.csv"
CSV_FIELDNAMES = ["title", "date", "url", "content", "tags"]

PAGE_SIZE   = 30    # jumlah artikel per halaman listing
MAX_RETRIES = 3     # percobaan ulang per request
BASE_DELAY  = 1.5   # jeda dasar antar request (detik)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Referer": BASE_URL,
}


# ── Session ────────────────────────────────────────────────────────────────────

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


# ── Pembantu paginasi ──────────────────────────────────────────────────────────

def listing_url_for_page(page_num: int) -> str:
    if page_num == 1:
        return LISTING_URL
    offset = (page_num - 1) * PAGE_SIZE
    return f"{LISTING_URL}/{offset}"


def get_max_listing_page(soup: BeautifulSoup) -> int:
    """
    Baca paginasi halaman listing dan kembalikan nomor halaman terakhir.
    Situs menyimpan nilai halaman di atribut data-ci-pagination-page.
    """
    try:
        links = soup.select("ul.pagination li a[data-ci-pagination-page]")
        max_page = 1
        for link in links:
            val = link.get("data-ci-pagination-page", "")
            if str(val).isdigit():
                n = int(val)
                if n > max_page:
                    max_page = n
        return max_page
    except Exception as exc:
        print(f"[PERINGATAN] Tidak dapat menentukan jumlah halaman: {exc}")
        return 1


# ── Wrapper retry ──────────────────────────────────────────────────────────────

def fetch_with_retry(
    session: requests.Session,
    url: str,
    delay: float,
    retries: int = MAX_RETRIES,
) -> BeautifulSoup | None:
    """
    GET url dengan percobaan ulang dan exponential backoff.
    Kembalikan BeautifulSoup jika berhasil, None jika semua percobaan gagal.
    """
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            time.sleep(delay + random.uniform(0, 0.8))
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as exc:
            wait = BASE_DELAY * (2 ** attempt)
            print(f"  [COBA {attempt}/{retries}] Error: {exc} — tunggu {wait:.1f}s")
            time.sleep(wait)
    return None


# ── Scraping halaman listing ───────────────────────────────────────────────────

def scrape_listing_page(
    session: requests.Session,
    url: str,
    delay: float,
) -> list[tuple[str, str]]:
    """
    Buka halaman listing dan kembalikan daftar (judul, url_artikel).
    Hanya mengambil h2.media-heading (bukan h4 di sidebar).
    """
    print(f"  Membuka halaman listing: {url}")
    soup = fetch_with_retry(session, url, delay)
    if soup is None:
        print(f"  [LEWATI] Gagal membuka halaman listing: {url}")
        return []

    articles: list[tuple[str, str]] = []
    for a_tag in soup.select("h2.media-heading a"):
        title = a_tag.get_text(strip=True)
        href  = a_tag.get("href", "")
        if href.startswith("/"):
            href = BASE_URL + href
        if title and href:
            articles.append((title, href))

    return articles


# ── Pembersih konten ───────────────────────────────────────────────────────────

_DOMAIN_WATERMARKS = (
    r"radartegal\.com",
    r"radartegal\.disway\.id",
)

_BOILERPLATE_PREFIXES = (
    "BACA JUGA",
    "Sumber:",
    "Simak breaking news",
    "Ikuti kami di Google News",
    "Dapatkan informasi terkini",
)

_BOILERPLATE_REGEX = re.compile(
    r"Cek Berita dan Artikel lainnya\s*di\s*Google\s*News"
    r"|Ikuti kami di Google News"
    r"|Simak breaking news"
    r"|Dapatkan informasi terkini",
    re.IGNORECASE,
)

_DOMAIN_REGEX = re.compile(
    "|".join(_DOMAIN_WATERMARKS),
    re.IGNORECASE,
)


def clean_content(text: str) -> str:
    """
    Bersihkan konten artikel dari teks sampah:
      - Domain watermark (radartegal.com, radartegal.disway.id)
      - Baris yang diawali prefix boilerplate
      - Baris footer Google News (berbagai variasi spasi)
      - Baris "Sumber:" dan turunannya
      - Baris pemisah "--" yang berdiri sendiri
      - Trailing "--" pada baris caption foto
      - Blok teks (*) / (*)
    """
    # Hapus domain watermark dari seluruh teks terlebih dahulu
    text = _DOMAIN_REGEX.sub("", text)
    # Hapus pola (*) / (**)
    text = re.sub(r"\(\*+\)", "", text)

    cleaned: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if any(line.startswith(prefix) for prefix in _BOILERPLATE_PREFIXES):
            continue
        if _BOILERPLATE_REGEX.search(line):
            continue
        if line == "--":
            continue
        line = re.sub(r"\s*--$", "", line).strip()
        if line:
            cleaned.append(line)
    return "\n".join(cleaned)


# ── Scraping artikel ───────────────────────────────────────────────────────────

def extract_article_content(soup: BeautifulSoup) -> tuple[str, str, str]:
    """
    Ekstrak data dari BeautifulSoup halaman artikel:
      - Tanggal: dari span.date
      - Isi: dari tag p dalam div.post.text-black-1
      - Tag: dari a[href*='/listtag/'] dalam ul.list-inline
    Kembalikan (tanggal, isi_bersih, tag_str). Tag dipisahkan " | ".
    """
    # Tanggal
    date_el  = soup.select_one("span.date")
    date_str = date_el.get_text(strip=True) if date_el else ""

    # Isi artikel
    content_div = soup.select_one("div.post.text-black-1")
    parts: list[str] = []
    if content_div:
        for p in content_div.find_all("p"):
            text = p.get_text(strip=True)
            if text:
                parts.append(text)

    # Tag artikel
    tag_list: list[str] = []
    for a in soup.select("ul.list-inline li a[href*='/listtag/']"):
        tag = a.get_text(strip=True).lstrip("#").strip()
        if tag:
            tag_list.append(tag)
    tags_str = _clean_tags(" | ".join(tag_list))

    return date_str, clean_content("\n".join(parts)), tags_str


def scrape_article(
    session: requests.Session,
    url: str,
    delay: float,
) -> tuple[str, str, str]:
    """
    Buka halaman artikel, ekstrak tanggal, isi, dan tag.
    Jika artikel memiliki paginasi internal (ul.pagination), ikuti semua halamannya.
    Tag hanya diambil dari halaman pertama.
    Kembalikan (tanggal, isi_lengkap, tag_str).
    """
    soup = fetch_with_retry(session, url, delay)
    if soup is None:
        return "", f"ERROR: gagal membuka {url}", ""

    date_str, body, tags_str = extract_article_content(soup)
    all_parts = [body] if body else []

    # Paginasi internal artikel
    visited: set[str] = {url}
    extra_urls: list[str] = []
    for link in soup.select("ul.pagination li a[data-ci-pagination-page]"):
        href = link.get("href", "")
        if href.startswith("/"):
            href = BASE_URL + href
        if href and href not in visited:
            extra_urls.append(href)
            visited.add(href)

    for extra_url in extra_urls:
        print(f"    -> halaman lanjutan artikel: {extra_url}")
        sub_soup = fetch_with_retry(session, extra_url, delay)
        if sub_soup:
            _, sub_body, _ = extract_article_content(sub_soup)
            if sub_body:
                all_parts.append(sub_body)

    return date_str, "\n\n".join(all_parts), tags_str


# ── Pembantu CSV ───────────────────────────────────────────────────────────────

def load_scraped_urls(output_file: str) -> set[str]:
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


# ── Orkestrator utama (standalone) ────────────────────────────────────────────

def run(
    start_page: int,
    end_page: int | None,
    delay: float,
):
    global _shutdown_requested

    session      = make_session()
    scraped_urls = load_scraped_urls(OUTPUT_FILE)
    append_mode  = len(scraped_urls) > 0
    fh, writer   = open_csv_writer(OUTPUT_FILE, append=append_mode)

    total_written = 0
    start_time    = time.time()

    try:
        print("Membuka halaman listing pertama untuk deteksi paginasi...")
        soup = fetch_with_retry(session, LISTING_URL, delay)
        if soup is None:
            print("[ERROR] Tidak bisa membuka halaman listing. Proses dihentikan.")
            return

        max_page      = get_max_listing_page(soup)
        effective_end = min(end_page, max_page) if end_page else max_page
        print(f"Total halaman listing: {max_page}")
        print(f"Scraping halaman {start_page} sampai {effective_end}")
        print("=" * 60)

        for page_num in range(start_page, effective_end + 1):
            if _shutdown_requested:
                break

            listing_url = listing_url_for_page(page_num)
            print(f"\n[Hal. {page_num}/{effective_end}] {listing_url}")

            articles = scrape_listing_page(session, listing_url, delay)
            print(f"  Ditemukan {len(articles)} artikel.")

            for idx, (title, article_url) in enumerate(articles, 1):
                if _shutdown_requested:
                    break

                if article_url in scraped_urls:
                    print(f"  [{idx}/{len(articles)}] Dilewati (sudah ada): {title[:55]}")
                    continue

                print(f"  [{idx}/{len(articles)}] {title[:65]}")
                try:
                    date_str, content, tags_str = scrape_article(session, article_url, delay)
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
        fh.close()

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"Selesai. {total_written} artikel ditulis ke {OUTPUT_FILE}")
    print(f"Durasi: {elapsed / 60:.1f} menit")
    print("=" * 60)


# ── API untuk dipanggil dari Flask ────────────────────────────────────────────

def scrape_new_articles(
    existing_urls: set,
    max_pages: int | None = None,
    on_progress=None,
) -> list[dict]:
    """
    Scrape berita baru dari RadarTegal (requests + BeautifulSoup).
    Berhenti begitu menemukan URL yang sudah ada di existing_urls.
    max_pages: batas jumlah halaman listing (None = semua).
    on_progress(count, msg): callback opsional untuk kirim pesan progress.
    Kembalikan list dict {title, date, url, content, tags}.
    """
    new_articles: list[dict] = []
    session = make_session()

    def log(msg: str):
        print(f"[RadarTegal] {msg}")
        if on_progress:
            on_progress(len(new_articles), msg)

    log("Membuka halaman listing untuk deteksi paginasi...")
    soup = fetch_with_retry(session, LISTING_URL, BASE_DELAY)
    if soup is None:
        log("[ERROR] Gagal membuka halaman listing.")
        return new_articles

    max_page = get_max_listing_page(soup)
    if max_pages is not None:
        max_page = min(max_page, max_pages)
    log(f"Total halaman listing: {max_page}")

    stop = False
    for page_num in range(1, max_page + 1):
        if stop:
            break

        listing_url = listing_url_for_page(page_num)
        log(f"[Hal. {page_num}] {listing_url}")

        # Halaman 1 sudah di-fetch untuk deteksi paginasi — pakai kembali
        if page_num == 1:
            page_soup = soup
        else:
            page_soup = fetch_with_retry(session, listing_url, BASE_DELAY)
            if page_soup is None:
                log(f"  [LEWATI] Gagal membuka halaman {page_num}")
                continue

        articles = []
        for a_tag in page_soup.select("h2.media-heading a"):
            title = a_tag.get_text(strip=True)
            href  = a_tag.get("href", "")
            if href.startswith("/"):
                href = BASE_URL + href
            if title and href:
                articles.append((title, href))

        log(f"  Ditemukan {len(articles)} artikel.")

        for idx, (title, article_url) in enumerate(articles, 1):
            if article_url in existing_urls:
                log(f"  [{idx}/{len(articles)}] Duplikat ditemukan, berhenti: {title[:55]}")
                stop = True
                break

            log(f"  [{idx}/{len(articles)}] Scraping: {title[:60]}")
            try:
                date_str, content, tags_str = scrape_article(session, article_url, BASE_DELAY)
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

    log(f"Total berita baru: {len(new_articles)}")
    return new_articles


# ── Entry point ────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scraper berita lokal radartegal.disway.id/kategori/lokal (requests+BS4)"
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
    print("Scraper Berita Lokal RadarTegal (requests + BeautifulSoup)")
    print("=" * 60)
    print(f"  Output   : {OUTPUT_FILE}")
    print(f"  Jeda     : {args.delay}s")
    print(f"  Halaman  : {args.start_page} sampai {args.end_page or 'terakhir'}")
    print()

    run(
        start_page=args.start_page,
        end_page=args.end_page,
        delay=args.delay,
    )
