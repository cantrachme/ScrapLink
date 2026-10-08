
from scrapling.fetchers import DynamicFetcher


def main():
    print("Testing JavaScript-rendered content...")

    page = DynamicFetcher.fetch(
        "https://quotes.toscrape.com/js/",
        headless=False,
        timeout=30000,
        wait_selector=".quote",
    )

    print("HTTP status:", page.status)

    quotes = page.css(".quote")

    print("Quotes found:", len(quotes))

    for quote in quotes[:3]:
        text = quote.css(".text::text").get()
        author = quote.css(".author::text").get()

        print(f"Quote: {text}")
        print(f"Author: {author}")
        print("---")

    assert page.status == 200
    assert len(quotes) > 0, "No JavaScript-rendered quotes found"

    print("Dynamic browser test PASSED!")


if __name__ == "__main__":
    main()
