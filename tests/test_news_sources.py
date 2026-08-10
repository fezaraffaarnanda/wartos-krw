import re
from pathlib import Path

import pytest

from config.region import FOCUS_AREA_SOURCES, NEWS_SOURCES, SOURCE_KEYS, SOURCE_LABELS

_ROOT = Path(__file__).resolve().parents[1]
_RE_SOURCE_KEY = re.compile(r"^[a-z][a-z0-9_]*$")


def test_keys_are_dom_id_safe():
    """Key dipakai sebagai suffix id DOM (bar-<key>); harus aman & stabil."""
    for key in SOURCE_KEYS:
        assert _RE_SOURCE_KEY.match(key), key


def test_progress_state_matches_sources():
    """Kalau state progress tidak punya key sumber, progress bar diam di 0% tanpa error."""
    from state.scraping import _scrape_progress

    assert set(_scrape_progress) == set(SOURCE_KEYS)


def test_scraper_registry_matches_sources():
    from services.article_pipeline import _build_scraper_config

    assert [k for k, _fn, _kw in _build_scraper_config(1)] == list(SOURCE_KEYS)


def test_focus_area_sources_match_labels():
    """Allowlist tampilan harus sama dengan label sumber yang benar-benar di-scrape."""
    assert set(FOCUS_AREA_SOURCES) == set(SOURCE_LABELS.values())


def test_api_sources_payload_shape():
    from services.scraping_service import ScrapingService

    payload, status = ScrapingService().list_sources()

    assert status == 200
    assert payload["status"] == "ok"
    assert payload["data"] == [{"key": k, "label": l} for k, l in NEWS_SOURCES]


_FRONTEND_FILES = (
    "templates/index.html",
    "static/js/dashboard/scrape.js",
    "static/js/dashboard/app_state.js",
    "static/js/shared/news_sources.js",
)
_FORBIDDEN = (
    "radartegal", "panturapost", "tribunjateng", "setdategal",
    "Radar Tegal", "Pantura Post", "Tribun Jateng", "Setda Tegal",
    "inews_karawang", "karawangnews", "pemda_karawang", "radar_karawang",
    "iNews Karawang", "KarawangNews", "Pemda Karawang", "Radar Karawang",
)


@pytest.mark.parametrize("rel_path", _FRONTEND_FILES)
def test_frontend_never_hardcodes_a_source(rel_path):
    """Frontend WAJIB mengambil daftar sumber dari GET /api/sources.

    Menuliskan nama/key sumber langsung di HTML atau JS adalah persis bug yang
    membuat semua progress bar diam di 0% saat migrasi Tegal -> Karawang.
    """
    text = (_ROOT / rel_path).read_text(encoding="utf-8")
    for token in _FORBIDDEN:
        assert token not in text, f"{rel_path} hardcode sumber '{token}'"
