
from backend.app.schemas.job import JobSearchRequest, JobSource


WELLFOUND_BASE_URL = "https://wellfound.com"

# Start with role pages that have been verified.
SUPPORTED_ROLES = {
    "software engineer": "software-engineer",
    "python developer": "python-developer",
    "full stack developer": "full-stack-developer",
    "data engineer": "data-engineer",
}

SUPPORTED_LOCATIONS = {
    "united states": "united-states",
    "new york": "new-york",
}


def build_wellfound_search_url(
    source: JobSource,
    search: JobSearchRequest,
) -> str:
    """
    Build a verified Wellfound public role-search URL.

    Arbitrary keyword searches are unsupported. Posting windows are
    validated locally after extraction; public role pages have no date filter.
    """

    if source != JobSource.WELLFOUND:
        raise ValueError(
            "Wellfound URL builder received an invalid source"
        )

    if search.source != JobSource.WELLFOUND.value:
        raise ValueError(
            "Search request source must be wellfound"
        )

    keyword = search.keyword.strip().casefold()

    if keyword not in SUPPORTED_ROLES:
        raise ValueError(
            f"Unsupported Wellfound role: {search.keyword}. "
            "Arbitrary keyword search is not implemented yet."
        )

    posted_window = search.date_posted or "any"

    if hasattr(posted_window, "value"):
        posted_window = posted_window.value

    if posted_window not in ("any", "24h", "7d", "30d"):
        raise ValueError(
            f"Unsupported date_posted filter: {posted_window}"
        )

    role_slug = SUPPORTED_ROLES[keyword]

    location = (search.location or "").strip().casefold()

    if not location:
        return (
            f"{WELLFOUND_BASE_URL}/role/{role_slug}"
        )

    if location not in SUPPORTED_LOCATIONS:
        raise ValueError(
            f"Unsupported Wellfound location: "
            f"{search.location}"
        )

    location_slug = SUPPORTED_LOCATIONS[location]

    return (
        f"{WELLFOUND_BASE_URL}/role/l/"
        f"{role_slug}/{location_slug}"
    )
