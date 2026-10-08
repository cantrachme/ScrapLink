
from datetime import date
from urllib.parse import urljoin

from backend.app.schemas.job import JobListing


class RealPythonDemoExtractor:
    SOURCE_URL = "https://realpython.github.io/fake-jobs/"

    def extract(self, page) -> list[JobListing]:
        jobs = []
        seen_urls = set()

        for card in page.css(".card"):
            title = card.css(".title::text").get()
            company = card.css(".company::text").get()
            location = card.css(".location::text").get()
            posted = card.css("time::attr(datetime)").get()
            links = card.css(
                ".card-footer a::attr(href)"
            ).getall()

            if not title or not company or not links:
                continue

            job_url = urljoin(self.SOURCE_URL, links[-1])

            if job_url in seen_urls:
                continue

            seen_urls.add(job_url)

            job = JobListing(
                title=title.strip(),
                company=company.strip(),
                location=location.strip() if location else None,
                job_url=job_url,
                source="realpython_demo",
                posted_date=date.fromisoformat(posted) if posted else None,
            )

            jobs.append(job)

        return jobs
