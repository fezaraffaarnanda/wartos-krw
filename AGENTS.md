# AGENTS.md

This file provides guidance to AI coding agents working in this repository.

## Project Overview

Flask news scraping dashboard for BPS (Badan Pusat Statistik). Scrapes 4 Indonesian news sources about the Tegal region and stores them in Supabase PostgreSQL. UI, comments, log messages, and docstrings are in **Bahasa Indonesia**. Deployed on Vercel.

## Commands

```bash
python app.py                                      # Run Flask dev server (localhost:5000)
python -m scrapers.scrape_radartegal_bs4            # Run RadarTegal scraper standalone
python -m scrapers.scraping_panturapost             # Run PanturaPost scraper standalone
python -m scrapers.scrape_tribunjateng_v2           # Run TribunJateng scraper standalone
python -m scrapers.scrape_kompas                    # Run Kompas scraper standalone
python tools/create_user.py <user> <pass> [role]    # Create user (role: admin/user)
pip install -r requirements.txt                     # Install dependencies
playwright install chromium                         # REQUIRED before running Kompas scraper
```

No test suite, linter, or formatter is configured. There is no `pyproject.toml`, `setup.py`, or `Makefile`.

## Project Structure

```
app.py                  # Flask app: routes, auth, scraping orchestration, threading
utils.py                # normalize_date(), parse_date_to_iso() — shared date utilities
requirements.txt        # pip dependencies (no pinned versions)
scrapers/               # One module per news source, each exports scrape_new_articles()
  __init__.py            # Empty
  scrape_radartegal_bs4.py   # RadarTegal — requests + BS4, offset-based pagination
  scraping_panturapost.py    # PanturaPost — requests + BS4
  scrape_tribunjateng_v2.py  # TribunJateng — requests + BS4
  scrape_kompas.py           # Kompas — requests + BS4 (was Playwright, now HTTP)
database/               # Raw SQL files — run manually in Supabase SQL Editor
  schema.sql             # Core berita table
  migration_*.sql        # Additive migrations (indexes, source column, users table)
templates/              # Jinja2-style HTML (served as static files via send_from_directory)
static/css/style.css    # Single stylesheet
static/js/script.js     # Single JS file — vanilla JS, no framework
tools/create_user.py    # CLI script to seed users into Supabase
```

## Critical Patterns

### Scraper API Contract

Every scraper module in `scrapers/` MUST export this function:

```python
def scrape_new_articles(existing_urls: set, max_articles: int, on_progress=None) -> list[dict]:
    # Returns list of: {"title", "date", "url", "content", "tags", "source"}
```

- `existing_urls`: set of URLs already in DB — scraper must stop when it hits a duplicate
- `on_progress(count, msg)`: optional callback for real-time progress updates
- `source`: string matching one of SOURCE_LABELS values in app.py:62 ("Radar Tegal", "Pantura Post", "Tribun Jateng", "Kompas")
- RadarTegal uses `max_pages` instead of `max_articles` — see `_build_scraper_config()` at app.py:431

### Date Normalization

ALL date strings from scrapers pass through `utils.normalize_date()` (utils.py:28) before DB insert. Target format: `"DD MMMM YYYY, HH:MM WIB"` (e.g., `"23 Februari 2026, 16:04 WIB"`). The companion `parse_date_to_iso()` (utils.py:79) converts to `"YYYY-MM-DD"` for the `date_parsed` column. Month names are in Bahasa Indonesia (Januari, Februari, Maret, etc.).

### Duplicate Detection

`_fetch_existing_urls()` (app.py:396) loads all URLs from Supabase before scraping begins. Scrapers receive this set and must stop pagination when they encounter a known URL. The `berita.url` column has a UNIQUE constraint.

### Threading & Shared State

`_scrape_progress` (app.py:315) and `_scrape_overall` (app.py:321) are module-level dicts shared across threads. Use `_scraping_lock` (app.py:313) when modifying. The lock is acquired in `start_scrape()` and released in `_scrape_worker()`'s `finally` block.

### Dual Auth on /api/scrape

`/api/scrape` (app.py:518) supports two auth modes:
1. Session auth (dashboard) → spawns background thread, returns immediately
2. `Authorization: Bearer <CRON_SECRET>` header → runs synchronously via `_scrape_sync()`

### Content Cleaning

Each scraper has its own `clean_content()` function that strips boilerplate (BACA JUGA, domain watermarks, editor/author lines, Google News footers). Pattern is consistent: regex domain removal → line-by-line prefix/regex filtering → rejoin.

## Database

Supabase PostgreSQL via `supabase-py` client. No ORM.

Tables:
- `berita`: `id, title, date, date_parsed, url (UNIQUE), content, tags, source, created_at`
- `scrape_log`: `id, total_inserted, scraped_at`
- `users`: `id, username, password_hash, role, created_at`

Queries use the Supabase fluent builder pattern:
```python
supabase.table("berita").select("*").eq("id", berita_id).single().execute()
```

## Environment Variables

Required in `.env`: `SUPABASE_URL`, `SUPABASE_KEY`, `FLASK_SECRET_KEY`, `CRON_SECRET`

If `FLASK_SECRET_KEY` is missing, a random key is generated (sessions won't persist across restarts).

## Code Style Guidelines

### Language

- All user-facing strings, log messages, comments, and docstrings: **Bahasa Indonesia**
- Variable/function names: English (snake_case), except domain terms like `berita`, `judul`, `tanggal`
- Internal scraper dicts may use Indonesian keys (`judul`, `tanggal`, `isi`, `waktu`) — these are mapped to English keys (`title`, `date`, `content`) in `scrape_new_articles()`

### Imports

- Standard library first, then third-party, then local — separated by blank lines
- Flask imports use parenthesized multi-line style (see app.py:7-17)
- Scraper imports in app.py use aliased form: `from scrapers.scrape_X import scrape_new_articles as scrape_X`

### Formatting

- 4-space indentation, no tabs
- Max line length ~100 chars (soft limit, not enforced)
- Section headers use box-drawing comment style: `# ── Section Name ──────────────────`
- Alignment padding with spaces for related assignments (e.g., app.py:48, app.py:79)
- Trailing commas in multi-line function calls and dicts
- Module-level constants: `UPPER_SNAKE_CASE`
- Private helpers: `_leading_underscore`

### Naming Conventions

- Functions/variables: `snake_case`
- Classes: `PascalCase` (only `User` class exists)
- Constants: `UPPER_SNAKE_CASE` (e.g., `SOURCE_LABELS`, `BERITA_LIST_COLUMNS`, `BASE_URL`)
- Module-level compiled regexes: `_UPPER_SNAKE_CASE` with leading underscore (e.g., `_PP_DOMAIN_REGEX`)
- Source key strings: lowercase, no spaces (`"radartegal"`, `"panturapost"`, `"tribunjateng"`, `"kompas"`)

### Type Hints

- Used on function signatures: `def func(param: str) -> dict | None:`
- Union syntax uses `X | Y` (Python 3.10+), not `Optional[X]` or `Union[X, Y]`
- Collection types use lowercase builtins: `list[dict]`, `set[str]`, `tuple[str, str]`
- Not used on local variables

### Error Handling

- Scrapers: catch `Exception` per-article, log with `print(f"[SOURCE] ...")`, continue to next
- DB operations: catch `Exception`, return error JSON with `{"status": "error", "message": "..."}` and appropriate HTTP status
- Log format: `[TAG] message` where TAG is source name or category (e.g., `[SCRAPE]`, `[DB ERROR]`, `[Kompas]`)
- Silent failures for non-critical ops (e.g., `_log_scrape_run` at app.py:388)
- Login errors use generic messages — never reveal whether username or password was wrong

### API Response Format

All JSON responses follow: `{"status": "ok"|"error", ...}` with optional `"data"`, `"message"` fields.

### Scraper Conventions

- Each scraper defines a `requests.Session` or uses `requests.get()` with browser-like `User-Agent` headers
- Rate limiting via `time.sleep(random.uniform(lo, hi))` between requests
- Each has a standalone `if __name__ == "__main__":` block for independent testing
- Content cleaning follows the same pattern across all scrapers (regex + line filtering)
- Inner `log()` closure for prefixed logging: `def log(msg): print(f"[SourceName] {msg}")`

## Gotchas

- Kompas scraper filters out "Jadwal Imsak" / "Jadwal Buka Puasa" articles (scrape_kompas.py:104)
- TribunJateng has double NA validation: once in the scraper (scrape_tribunjateng_v2.py:284) and once in `_is_valid_article()` (app.py:339)
- PanturaPost internal article keys are Indonesian (`judul`, `tanggal`, `isi`), Kompas uses capitalized Indonesian (`Judul`, `Tanggal`, `Isi`) — both mapped in `scrape_new_articles()`
- Vercel serverless may timeout on full scrape — cron mode uses `_scrape_sync()` which runs sequentially
- Login rate limit: 5 attempts per 15 minutes (app.py:141)
- `requirements.txt` has no pinned versions — builds may break on dependency updates
