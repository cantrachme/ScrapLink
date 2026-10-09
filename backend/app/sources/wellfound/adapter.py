
import json
import re
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
from backend.app.services.job_deduplication import (
    deduplicate_job_urls,
    normalize_job_url,
)
from backend.app.services.job_filters import parse_posting_date
from backend.app.sources.structured_job import compensation, employment_type, workplace_type


class WellfoundJobAdapter(BaseJobSourceAdapter):
    source = JobSource.WELLFOUND
    allowed_domains = ("wellfound.com",)

    BASE_URL = "https://wellfound.com/jobs"

    JOB_PATH = re.compile(
        r"/jobs/(\d+)(?:-[^/]*)?/?$"
    )

    def _valid_job_url(self, href: str) -> str | None:
        url = normalize_source_job_url(
            href,
            self.BASE_URL,
            self.allowed_domains,
        )

        if not url:
            return None

        parsed = urlsplit(url)

        if not self.JOB_PATH.fullmatch(parsed.path):
            return None

        return normalize_job_url(self.source, url)

    def discover_job_urls(
        self,
        page: Selector,
        search: JobSearchRequest,
    ) -> list[str]:

        urls = []

        links = page.css(
            'a[href*="/jobs/"]::attr(href)'
        ).getall()

        for href in links:
            url = self._valid_job_url(str(href))

            if not url:
                continue

            urls.append(url)

        return deduplicate_job_urls(self.source, urls)

    @staticmethod
    def _structured_job(page: Selector) -> dict:
        scripts = page.css(
            'script[type="application/ld+json"]::text'
        ).getall()

        for script in scripts:
            try:
                data = json.loads(str(script))
            except (ValueError, TypeError):
                continue

            stack = [data]

            while stack:
                item = stack.pop()

                if isinstance(item, list):
                    stack.extend(item)
                    continue

                if not isinstance(item, dict):
                    continue

                types = item.get("@type", [])
                if isinstance(types, str):
                    types = [types]

                if isinstance(types, list) and any(
                    isinstance(t, str)
                    and t.split("/")[-1] == "JobPosting"
                    for t in types
                ):
                    return item

                if "@graph" in item:
                    stack.append(item["@graph"])

        return {}

    @staticmethod
    def _first_text(page, selectors):
        for selector in selectors:
            value = page.css(selector).get()

            if value and str(value).strip():
                return str(value).strip()

        return None

    @staticmethod
    def _html_to_text(value):
        if not isinstance(value, str) or not value.strip():
            return None

        parser = Selector(content=f"<div>{value}</div>")

        text = parser.get_all_text(
            separator="\n",
            strip=True,
        )

        return str(text).strip() or None

    @staticmethod
    def _get_location(data):
        location = data.get("jobLocation")

        if isinstance(location, list):
            location = location[0] if location else None

        if not isinstance(location, dict):
            return None

        address = location.get("address")

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
            str(p) for p in parts if p
        ) or None

    def extract_job_details(
        self,
        page: Selector,
        job_url: str,
    ) -> JobListing:

        url = self._valid_job_url(job_url)

        if not url:
            raise ValueError("Invalid Wellfound job URL")

        structured = self._structured_job(page)

        organization = structured.get(
            "hiringOrganization", {}
        )

        if isinstance(organization, list):
            organization = (
                organization[0] if organization else {}
            )

        if not isinstance(organization, dict):
            organization = {}

        title = structured.get("title") or self._first_text(
            page,
            ["h1::text"],
        )

        company = organization.get("name") or self._first_text(
            page,
            [
                '[data-testid="company-name"]::text',
                'a[href*="/company/"]::text',
            ],
        )

        if not title:
            raise ValueError(
                "Missing required Wellfound job details"
            )

        description = self._html_to_text(
            structured.get("description")
        )

        if not description:
            selectors = [
                '[data-testid="job-description"]',
                '[itemprop="description"]',
                'section[aria-label="About the job"]',
                ".job-description",
            ]

            for selector in selectors:
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

        posted_date, posted_at = parse_posting_date(structured.get("datePosted"))

        location = self._get_location(
            structured
        ) or self._first_text(
            page,
            ['[data-testid="job-location"]::text'],
        )

        skills = []
        seen_skills = set()

        for skill in page.css(
            '[data-testid="job-skills"] li::text'
        ).getall():
            value = str(skill).strip()

            if value and value.lower() not in seen_skills:
                skills.append(value)
                seen_skills.add(value.lower())

        parsed_employment = employment_type(
            structured.get("employmentType")
            or self._first_text(
                page,
                ['[data-testid="employment-type"]::text'],
            )
        )

        parsed_workplace = workplace_type(
            structured.get("jobLocationType")
            or self._first_text(
                page,
                ['[data-testid="remote-work-policy"]::text'],
            )
        )

        job_id = self.JOB_PATH.fullmatch(
            urlsplit(url).path
        ).group(1)

        return JobListing(
            source=self.source,
            source_job_id=job_id,
            job_url=url,
            title=str(title).strip(),
            company=str(company or "").strip(),
            company_url=organization.get("sameAs"),
            description=description,
            location=location,
            employment_type=parsed_employment,
            workplace_type=parsed_workplace,
            skills=skills,
            compensation=compensation(
                structured
            ),
            posted_date=posted_date,
            posted_at=posted_at,
        )
