
from scrapling.fetchers import DynamicFetcher


def main():
    print("Launching Chromium...")

    page = DynamicFetcher.fetch(
        "https://example.com",
        headless=False,
        timeout=30000,
    )

    print("HTTP status:", page.status)
    print("Page title:", page.css("title::text").get())
    print("Links found:", len(page.css("a")))

    assert page.status == 200, "Page request failed"
    assert page.css("title::text").get(), "Page title not found"

    print("Browser test PASSED!")


if __name__ == "__main__":
    main()
