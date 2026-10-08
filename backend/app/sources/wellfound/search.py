
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

    This does not support arbitrary keyword searches
    or date filters. Those require further integration.
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

    if posted_window != "any":
        raise ValueError(
            "Wellfound date_posted filtering is not "
            "implemented yet. Use date_posted='any'."
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
