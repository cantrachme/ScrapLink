"""Pagination for public listing pages only; never follow arbitrary next links."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from backend.app.schemas.job import JobSearchRequest, JobSource
from backend.app.sources.linkedin.search import build_linkedin_search_url
from backend.app.sources.wellfound.search import build_wellfound_search_url


def paginate_search_url(source: JobSource, url: str, page_number: int) -> str:
    """Paginate an existing source URL, retaining its search parameters."""
    if type(page_number) is not int or page_number < 1:
        raise ValueError("page_number must be a positive integer")

    parsed = urlsplit(url)
    hosts = {
        JobSource.LINKEDIN: {"linkedin.com", "www.linkedin.com"},
        JobSource.WELLFOUND: {"wellfound.com", "www.wellfound.com"},
    }
    if source not in hosts:
        raise ValueError(f"Unsupported job source: {source}")
    if (
        parsed.scheme != "https"
        or parsed.hostname not in hosts[source]
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
    ):
        raise ValueError("Pagination requires an HTTPS URL on the source domain")

    if source == JobSource.LINKEDIN:
        if parsed.path.rstrip("/") != "/jobs/search":
            raise ValueError("LinkedIn pagination requires a /jobs/search/ page")
        parameter, offset = "start", (page_number - 1) * 25
    else:
        if not parsed.path.startswith("/role/") or not parsed.path[6:].strip("/"):
            raise ValueError("Wellfound pagination supports public /role/ pages only")
        parameter, offset = "page", page_number

    if page_number == 1:
        return url

    params = [
        (key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key != parameter
    ]
    params.append((parameter, str(offset)))
    return urlunsplit(parsed._replace(query=urlencode(params)))


def build_paginated_search_url(
    source: JobSource,
    search: JobSearchRequest,
    page_number: int,
) -> str:
    if source == JobSource.LINKEDIN:
        url = build_linkedin_search_url(source, search)
    elif source == JobSource.WELLFOUND:
        url = build_wellfound_search_url(source, search)
    else:
        raise ValueError(f"Unsupported job source: {source}")
    return paginate_search_url(source, url, page_number)
