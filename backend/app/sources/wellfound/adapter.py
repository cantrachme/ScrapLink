
import json
import re
from datetime import date
from urllib.parse import urlsplit, urlunsplit

from scrapling.parser import Selector

from backend.app.schemas.job import (
    Compensation,
    EmploymentType,
    JobListing,
    JobSearchRequest,
    JobSource,
    WorkplaceType,
)
from backend.app.sources.base import (
    BaseJobSourceAdapter,
    normalize_source_job_url,
)


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

        # Remove tracking query parameters and fragments.
        return urlunsplit((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            "",
            "",
        ))

    def discover_job_urls(
        self,
        page: Selector,
        search: JobSearchRequest,
    ) -> list[str]:

        urls = []
        seen = set()

        links = page.css(
            'a[href*="/jobs/"]::attr(href)'
        ).getall()

        for href in links:
            url = self._valid_job_url(str(href))

            if not url or url in seen:
                continue

            seen.add(url)
            urls.append(url)

            if len(urls) >= search.max_results:
                break

        return urls

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

    @staticmethod
    def _get_employment_type(value):
        if not isinstance(value, str):
            return None

        normalized = value.strip().lower()
        normalized = normalized.replace("-", "_")
        normalized = normalized.replace(" ", "_")

        mapping = {
            "full_time": EmploymentType.FULL_TIME,
            "fulltime": EmploymentType.FULL_TIME,
            "part_time": EmploymentType.PART_TIME,
            "contract": EmploymentType.CONTRACT,
            "internship": EmploymentType.INTERNSHIP,
            "temporary": EmploymentType.TEMPORARY,
        }

        return mapping.get(normalized)

    @staticmethod
    def _get_workplace_type(value):
        if not isinstance(value, str):
            return None

        normalized = value.strip().lower()

        mapping = {
            "telecommute": WorkplaceType.REMOTE,
            "remote": WorkplaceType.REMOTE,
            "remote only": WorkplaceType.REMOTE,
            "in office": WorkplaceType.ONSITE,
            "onsite": WorkplaceType.ONSITE,
            "hybrid": WorkplaceType.HYBRID,
        }

        return mapping.get(normalized)

    @staticmethod
    def _get_compensation(data):
        salary = data.get("baseSalary")

        if not isinstance(salary, dict):
            return None

        value = salary.get("value", {})

        if isinstance(value, (int, float)):
            value = {
                "minValue": value,
                "maxValue": value,
            }

        if not isinstance(value, dict):
            return None

        period_map = {
            "HOUR": "hour",
            "MONTH": "month",
            "YEAR": "year",
        }

        period = period_map.get(
            str(value.get("unitText", "")).upper()
        )

        return Compensation(
            currency=salary.get("currency"),
            min_amount=value.get("minValue"),
            max_amount=value.get("maxValue"),
            period=period,
        )

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

        if not title or not company:
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

        raw_date = structured.get("datePosted")
        posted_date = None

        if raw_date:
            try:
                posted_date = date.fromisoformat(
                    str(raw_date)[:10]
                )
            except ValueError:
                pass

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

        employment_type = self._get_employment_type(
            structured.get("employmentType")
            or self._first_text(
                page,
                ['[data-testid="employment-type"]::text'],
            )
        )

        workplace_type = self._get_workplace_type(
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
            company=str(company).strip(),
            company_url=organization.get("sameAs"),
            description=description,
            location=location,
            employment_type=employment_type,
            workplace_type=workplace_type,
            skills=skills,
            compensation=self._get_compensation(
                structured
            ),
            posted_date=posted_date,
        )
