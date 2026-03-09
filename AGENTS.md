# AGENTS.md

This file provides guidance to AI coding agents working in this repository.

## Project Overview

Flask news scraping dashboard for BPS (Badan Pusat Statistik). Scrapes 5 Indonesian news sources about the Tegal region and stores them in Supabase PostgreSQL. Includes AI-powered insights using DeepSeek LLM for analyzing PDRB, Kemiskinan, and Pengangguran trends. UI, comments, log messages, and docstrings are in **Bahasa Indonesia**. Deployed on Vercel.

## Initialization

```bash
# 1. Clone repository and navigate to project directory
cd "C:\Users\fezaa\OneDrive\Documents\01. BPS\SCRAPING"

# 2. Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install Playwright browser (required for Kompas scraper)
playwright install chromium

# 5. Configure environment variables
# Create .env file with:
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_anon_key
FLASK_SECRET_KEY=your_random_secret_key_here
CRON_SECRET=your_cron_secret_for_api_auth
DEEPSEEK_API_KEY=your_deepseek_api_key  # For AI insights feature

# 6. Initialize database (run SQL files in Supabase SQL Editor)
# - database/schema.sql (core tables)
# - database/migration_*.sql (in order)

# 7. Create initial admin user
python tools/create_user.py admin your_password admin

# 8. Run development server
python app.py  # Access at http://localhost:5000
```

## Commands

```bash
python app.py                                      # Run Flask dev server (localhost:5000)
python -m scrapers.scrape_radartegal_bs4            # Run RadarTegal scraper standalone
python -m scrapers.scraping_panturapost             # Run PanturaPost scraper standalone
python -m scrapers.scrape_tribunjateng_v2           # Run TribunJateng scraper standalone
python -m scrapers.scrape_kompas                    # Run Kompas scraper standalone
python -m scrapers.scraping_tegal                   # Run Setda Tegal scraper standalone
python tools/create_user.py <user> <pass> [role]    # Create user (role: admin/user)
pip install -r requirements.txt                     # Install dependencies
playwright install chromium                         # REQUIRED before running Kompas scraper
```

No test suite, linter, or formatter is configured. There is no `pyproject.toml`, `setup.py`, or `Makefile`.

## Project Structure

```
app.py                  # Flask app: routes, auth, scraping orchestration, threading
utils.py                # normalize_date(), parse_date_to_iso() — shared date utilities
ai_insights.py          # AI insights using DeepSeek LLM for PDRB/Kemiskinan/Pengangguran
requirements.txt        # pip dependencies (no pinned versions)
scrapers/               # One module per news source, each exports scrape_new_articles()
  __init__.py            # Empty
  scrape_radartegal_bs4.py   # RadarTegal — requests + BS4, offset-based pagination
  scraping_panturapost.py    # PanturaPost — requests + BS4
  scrape_tribunjateng_v2.py  # TribunJateng — requests + BS4
  scrape_kompas.py           # Kompas — requests + BS4 (was Playwright, now HTTP)
  scraping_tegal.py          # Setda Tegal — requests + BS4, JNews theme
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
- `source`: string matching one of SOURCE_LABELS values in app.py:64 ("Radar Tegal", "Pantura Post", "Tribun Jateng", "Kompas", "Setda Tegal")
- RadarTegal uses `max_pages` instead of `max_articles` — see `_build_scraper_config()` in app.py

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

### AI Insights Feature

`ai_insights.py` provides AI-powered analysis using DeepSeek LLM:
- `generate_insights(articles: list[dict]) -> dict`: Analyzes articles for PDRB, Kemiskinan, Pengangguran trends
- Pre-filters articles by keywords per category (ai_insights.py:27-49)
- Limits to 30 articles per category, 500 chars per article content (token optimization)
- Returns structured insights with summaries, trends, and source references
- Requires `DEEPSEEK_API_KEY` in environment variables
- Called from `/api/insights` endpoint in app.py

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

Required in `.env`:
- `SUPABASE_URL`: Supabase project URL
- `SUPABASE_KEY`: Supabase anon/service key
- `FLASK_SECRET_KEY`: Flask session secret (auto-generated if missing, but sessions won't persist)
- `CRON_SECRET`: Bearer token for `/api/scrape` cron authentication
- `DEEPSEEK_API_KEY`: DeepSeek API key for AI insights feature (optional, required for insights)

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
- Source key strings: lowercase, no spaces (`"radartegal"`, `"panturapost"`, `"tribunjateng"`, `"kompas"`, `"setdategal"`)

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
- TribunJateng has double NA validation: once in the scraper and once in `_is_valid_article()` in app.py
- PanturaPost internal article keys are Indonesian (`judul`, `tanggal`, `isi`), Kompas uses capitalized Indonesian (`Judul`, `Tanggal`, `Isi`) — both mapped in `scrape_new_articles()`
- Setda Tegal uses JNews WordPress theme with specific date format parsing (scraping_tegal.py:34-48)
- Vercel serverless may timeout on full scrape — cron mode uses `_scrape_sync()` which runs sequentially
- Login rate limit: 5 attempts per 15 minutes (app.py:141)
- `requirements.txt` has no pinned versions — builds may break on dependency updates
- AI insights feature requires OpenAI-compatible client but uses DeepSeek endpoint (ai_insights.py:16-17)
- DeepSeek responses are parsed as JSON — malformed responses will cause insight generation to fail
