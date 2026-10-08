
from scrapling.fetchers import DynamicFetcher

from backend.app.config import settings


class ScrapingWorker:
    def __init__(self):
        self.headless = settings.BROWSER_HEADLESS
        self.timeout = settings.BROWSER_TIMEOUT_MS

    def fetch_page(self, url: str):
        """Fetch a JavaScript-rendered page using Chromium."""

        return DynamicFetcher.fetch(
            url,
            headless=self.headless,
            timeout=self.timeout,
        )

    def extract_page_info(self, url: str) -> dict:
        """Extract basic information from a webpage."""

        page = self.fetch_page(url)

        return {
            "url": url,
            "status_code": page.status,
            "title": page.css("title::text").get(),
            "links_count": len(page.css("a")),
        }
