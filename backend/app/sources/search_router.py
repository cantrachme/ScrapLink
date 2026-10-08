
from backend.app.schemas.job import JobSearchRequest, JobSource

from backend.app.sources.linkedin.search import (
    build_linkedin_search_url,
)
from backend.app.sources.wellfound.search import (
    build_wellfound_search_url,
)


def build_source_search_url(
    source: JobSource,
    search: JobSearchRequest,
) -> str:
    """Route a job search to its source-specific builder."""

    if source == JobSource.LINKEDIN:
        return build_linkedin_search_url(source, search)

    if source == JobSource.WELLFOUND:
        return build_wellfound_search_url(source, search)

    raise ValueError(f"Unsupported job source: {source}")
