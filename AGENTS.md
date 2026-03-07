# AGENTS.md — Coding Agent Instructions

## Project Overview

Python Flask web application: a news scraping dashboard for BPS (Badan Pusat Statistik)
that scrapes articles from 4 Indonesian news sources about the Tegal region.
UI and code comments are in **Bahasa Indonesia**.

### Tech Stack

- **Backend**: Flask, Flask-Login, Flask-Bcrypt, Flask-Limiter
- **Scraping**: requests + BeautifulSoup4, Playwright (Kompas)
- **Database**: Supabase (PostgreSQL) via `supabase-py`
- **Frontend**: Jinja2 templates, vanilla JS, CSS
- **Deployment**: Vercel (serverless) + local threaded mode
- **Python**: 3.10+ (uses `str | None`, `list[dict]` syntax)

### Directory Structure

```
app.py                  # Main Flask app — routes, auth, scraping orchestration
utils.py                # Date normalization utilities
requirements.txt        # Python dependencies
scrapers/               # One module per news source
  __init__.py
  scrape_radartegal_bs4.py
  scraping_panturapost.py
  scrape_tribunjateng_v2.py
  scrape_kompas.py
tools/
  create_user.py        # CLI tool to create users in Supabase
database/               # SQL migration files
templates/              # Jinja2 HTML templates
static/                 # JS, CSS, images
```

---

## Build / Run Commands

### Setup

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
playwright install chromium     # Required for Kompas scraper
```

### Run locally

```bash
python app.py
```

The app starts on `http://localhost:5000` with threaded scraping enabled.

### Run a single scraper standalone

Each scraper has an `if __name__ == "__main__"` block:

```bash
python -m scrapers.scrape_radartegal_bs4
python -m scrapers.scraping_panturapost
python -m scrapers.scrape_tribunjateng_v2
python -m scrapers.scrape_kompas
```

### Create a user

```bash
python tools/create_user.py
```

### Tests

There is **no test suite**. No pytest, unittest, or test files exist.
If adding tests, use `pytest` and place them in a `tests/` directory.

### Linting

There is **no linter configuration**. No flake8, ruff, or pyproject.toml.
If adding a linter, use `ruff` with default settings.

---

## Environment Variables

Required in `.env` (loaded via `python-dotenv`):

- `SUPABASE_URL` — Supabase project URL
- `SUPABASE_KEY` — Supabase anon/service key
- `FLASK_SECRET_KEY` — Flask session secret
- `CRON_SECRET` — Secret for cron endpoint authentication

**Never commit `.env` or secrets to the repository.**

---

## Code Style

### Imports

1. Standard library imports first
2. Third-party imports second
3. Local imports third
4. Separate each group with a blank line
5. Flask multi-line imports use parenthesized form

```python
import os
import json
from datetime import datetime

from flask import Flask, request, jsonify
from supabase import create_client

from scrapers.scrape_kompas import scrape_new_articles
```

### Naming

- **Functions / variables**: `snake_case`
- **Classes**: `PascalCase` (only `User` class exists)
- **Private functions / variables**: prefix with `_` (e.g., `_scrape_progress`, `_insert_articles`)
- **Constants**: not formally distinguished; use `UPPER_SNAKE_CASE` for new constants

### Type Hints

Used sparingly. When present, use Python 3.10+ syntax:

```python
def normalize_date(raw: str) -> str | None:
    ...

def scrape_new_articles(existing_urls: set, max_articles: int, on_progress=None) -> list[dict]:
    ...
```

### Section Headers

Use Unicode box-drawing comment style for major sections:

```python
# ── Section Name ──────────────────────────────────────
```

### Docstrings

Not enforced project-wide. Key functions have triple-quote docstrings.
When adding docstrings, use simple triple-quote style (no reStructuredText or Google style).

### Error Handling

- Broad `except Exception` with `print()` logging is the current pattern
- Generic error messages are returned to users (no stack traces exposed)
- Prefer this pattern for consistency, but add specific exception types when feasible

### Scraper Module Convention

Every scraper module must follow this structure:

1. A public `scrape_new_articles(existing_urls: set, max_articles: int, on_progress=None) -> list[dict]` function — this is the API called by `app.py`
2. A `clean_content(text: str) -> str` function for source-specific boilerplate removal
3. A standalone `if __name__ == "__main__"` block for independent testing
4. Each returned article dict must contain: `judul`, `tanggal`, `url`, `konten`, `source`

### Article Dict Schema

```python
{
    "judul": str,       # Article title
    "tanggal": str,     # Publication date (normalized via utils.normalize_date)
    "url": str,         # Full article URL
    "konten": str,      # Cleaned article content
    "source": str,      # Source name: "Radar Tegal", "Pantura Post", "Tribun Jateng", "Kompas"
}
```

### Language

- Code comments, log messages, and variable names may be in Indonesian
- Keep new code consistent with surrounding context
- UI strings are in Indonesian — do not translate them to English

---

## Architecture Notes

### Scraping Modes

- **Local / threaded**: `app.py` uses `threading.Thread` + `threading.Lock` for concurrent scraping with progress tracking via `_scrape_progress` global dict
- **Vercel / serverless**: synchronous scraping (no threads), triggered via cron endpoint with `CRON_SECRET` auth

### Database

- Supabase PostgreSQL with tables: `articles`, `scrape_logs`, `users`
- Schema and migrations live in `database/` directory
- All DB operations go through `supabase-py` client (no ORM)

### Auth

- Flask-Login with bcrypt password hashing
- User records stored in Supabase `users` table
- Rate limiting via Flask-Limiter on login endpoint

---

## Common Pitfalls

- **Playwright**: The Kompas scraper requires `playwright install chromium`. It will fail silently or crash without it.
- **Global mutable state**: `_scrape_progress` dict is shared across threads — always use `_progress_lock` when reading/writing.
- **Date parsing**: Indonesian date strings are inconsistent across sources. Always route through `utils.normalize_date()`.
- **Duplicate detection**: `app.py` fetches existing URLs from Supabase before scraping to avoid duplicates. Scrapers receive these as `existing_urls` parameter.
- **Vercel cold starts**: Serverless functions have tight timeouts. Scraping all sources may exceed limits.
