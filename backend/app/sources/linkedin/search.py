
from urllib.parse import quote, urlencode

from backend.app.schemas.job import (
    JobSearchRequest,
    JobSource,
)


LINKEDIN_JOBS_SEARCH_URL = (
    "https://www.linkedin.com/jobs/search/"
)

DATE_POSTED_FILTERS = {
    "24h": "r86400",
    "7d": "r604800",
    "30d": "r2592000",
}


def build_linkedin_search_url(
    source: JobSource,
    search: JobSearchRequest,
) -> str:
    """
    Build a LinkedIn Jobs search URL.

    This function only constructs a URL.
    It does not make a network request.
    """

    if source != JobSource.LINKEDIN:
        raise ValueError(
            "LinkedIn URL builder received an invalid source"
        )

    if search.source != JobSource.LINKEDIN.value:
        raise ValueError(
            "Search request source must be linkedin"
        )

    keyword = search.keyword.strip()

    if not keyword:
        raise ValueError(
            "Job search keyword cannot be empty"
        )

    params = {
        "keywords": keyword,
        "sortBy": "DD",
    }

    if search.location and search.location.strip():
        params["location"] = search.location.strip()

    posting_window = search.date_posted or "any"

    if hasattr(posting_window, "value"):
        posting_window = posting_window.value

    if posting_window not in (
        "any",
        "24h",
        "7d",
        "30d",
    ):
        raise ValueError(
            f"Unsupported date_posted filter: {posting_window}"
        )

    if posting_window in DATE_POSTED_FILTERS:
        params["f_TPR"] = DATE_POSTED_FILTERS[
            posting_window
        ]

    query_string = urlencode(
        params,
        quote_via=quote,
    )

    return f"{LINKEDIN_JOBS_SEARCH_URL}?{query_string}"
