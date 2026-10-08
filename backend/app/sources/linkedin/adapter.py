
import json
import re
from datetime import date
from urllib.parse import urlsplit

from scrapling.parser import Selector

from backend.app.schemas.job import (
    JobListing,
    JobSearchRequest,
    JobSource,
)
from backend.app.sources.base import (
    BaseJobSourceAdapter,
    normalize_source_job_url,
)


class LinkedInJobAdapter(BaseJobSourceAdapter):
    source = JobSource.LINKEDIN
    allowed_domains = ("linkedin.com",)

    BASE_URL = "https://www.linkedin.com/jobs/"

    def discover_job_urls(
        self,
        page: Selector,
        search: JobSearchRequest,
    ) -> list[str]:
        """Discover unique job URLs from supplied HTML."""

        urls = []
        seen = set()

        links = page.css(
            'a[href*="/jobs/view/"]::attr(href)'
        ).getall()

        for href in links:
            url = normalize_source_job_url(
                str(href),
                self.BASE_URL,
                self.allowed_domains,
            )

            if not url:
                continue

            if not urlsplit(url).path.startswith(
                "/jobs/view/"
            ):
                continue

            if url not in seen:
                seen.add(url)
                urls.append(url)

            if len(urls) >= search.max_results:
                break

        return urls

    @staticmethod
    def _get_structured_job(page: Selector) -> dict:
        """Find a JobPosting JSON-LD object."""

        scripts = page.css(
            'script[type="application/ld+json"]::text'
        ).getall()

        for script in scripts:
            try:
                data = json.loads(str(script))
            except (ValueError, TypeError):
                continue

            nodes = data if isinstance(data, list) else [data]

            for node in nodes:
                if not isinstance(node, dict):
                    continue

                graph = node.get("@graph")
                candidates = (
                    graph if isinstance(graph, list)
                    else [node]
                )

                for item in candidates:
                    if not isinstance(item, dict):
                        continue

                    job_type = item.get("@type", "")
                    types = (
                        job_type if isinstance(job_type, list)
                        else [job_type]
                    )

                    if any(
                        isinstance(t, str)
                        and t.endswith("JobPosting")
                        for t in types
                    ):
                        return item

        return {}

    @staticmethod
    def _first_text(page: Selector, selectors: list[str]):
        for selector in selectors:
            text = page.css(selector).get()
            if text and str(text).strip():
                return str(text).strip()
        return None

    @staticmethod
    def _location(data: dict) -> str | None:
        place = data.get("jobLocation")

        if isinstance(place, list):
            place = place[0] if place else None

        if not isinstance(place, dict):
            return None

        address = place.get("address", {})

        if isinstance(address, str):
            return address.strip() or None

        if not isinstance(address, dict):
            return None

        parts = [
            address.get("addressLocality"),
            address.get("addressRegion"),
            address.get("addressCountry"),
        ]

        return ", ".join(
            str(part) for part in parts if part
        ) or None

    @staticmethod
    def _description_to_text(raw: str | None):
        if not raw:
            return None

        parsed = Selector(
            content=f"<section>{raw}</section>"
        )

        text = str(
            parsed.get_all_text(
                separator="\n",
                strip=True,
            )
        ).strip()

        return text or None

    def extract_job_details(
        self,
        page: Selector,
        job_url: str,
    ) -> JobListing:
        """Parse a LinkedIn job page from supplied HTML."""

        url = normalize_source_job_url(
            job_url,
            self.BASE_URL,
            self.allowed_domains,
        )

        if not url or not urlsplit(url).path.startswith(
            "/jobs/view/"
        ):
            raise ValueError("Invalid LinkedIn job URL")

        data = self._get_structured_job(page)

        organization = data.get("hiringOrganization", {})
        if isinstance(organization, list):
            organization = (
                organization[0] if organization else {}
            )
        if not isinstance(organization, dict):
            organization = {}

        title = data.get("title") or self._first_text(
            page,
            [
                "h1.top-card-layout__title::text",
                "h1::text",
            ],
        )

        company = organization.get("name") or self._first_text(
            page,
            [
                "a.topcard__org-name-link::text",
                ".topcard__flavor::text",
            ],
        )

        if not title or not company:
            raise ValueError(
                "Missing required LinkedIn job details"
            )

        description = self._description_to_text(
            data.get("description")
        )

        if not description:
            for selector in [
                ".show-more-less-html__markup",
                ".description__text",
                ".jobs-description__content",
            ]:
                elements = page.css(selector)
                if elements:
                    description = str(
                        elements[0].get_all_text(
                            separator="\n",
                            strip=True,
                        )
                    ).strip() or None
                    if description:
                        break

        posted_date = None
        raw_date = data.get("datePosted")

        if raw_date:
            try:
                posted_date = date.fromisoformat(
                    str(raw_date)[:10]
                )
            except ValueError:
                pass

        location = self._location(data) or self._first_text(
            page,
            [".topcard__flavor--bullet::text"],
        )

        match = re.search(
            r"(\d+)/?$",
            urlsplit(url).path,
        )

        return JobListing(
            source=self.source,
            source_job_id=match.group(1) if match else None,
            job_url=url,
            title=str(title).strip(),
            company=str(company).strip(),
            company_url=organization.get("sameAs"),
            location=location,
            description=description,
            posted_date=posted_date,
        )
