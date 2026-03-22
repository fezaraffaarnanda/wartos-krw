"""
Kontrak typing untuk scraper module.
"""

from typing import Protocol


class ProgressCallback(Protocol):
    """Callback opsional untuk update progress scraping."""

    def __call__(self, count: int, msg: str = "") -> None:
        ...


class ScraperContract(Protocol):
    """Kontrak fungsi scraper per sumber berita."""

    def scrape_new_articles(
        self,
        existing_urls: set,
        max_articles: int,
        on_progress: ProgressCallback | None = None,
    ) -> list[dict]:
        ...
