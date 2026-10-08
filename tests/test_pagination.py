from urllib.parse import parse_qs, urlsplit

import pytest

from backend.app.schemas.job import JobSearchRequest, JobSource
from backend.app.sources.pagination import build_paginated_search_url, paginate_search_url
from backend.app.sources.search_router import build_source_search_url


@pytest.mark.parametrize("source", [JobSource.LINKEDIN, JobSource.WELLFOUND])
@pytest.mark.parametrize("page", [1, 2, 3])
def test_paginated_search_urls(source, page):
    request = JobSearchRequest(
        source=source.value, keyword="Python Developer", date_posted="7d",
    )
    url = build_paginated_search_url(source, request, page)
    params = parse_qs(urlsplit(url).query)
    if page == 1:
        assert url == build_source_search_url(source, request)
        assert "start" not in params and "page" not in params
    if source == JobSource.LINKEDIN:
        assert urlsplit(url).path == "/jobs/search/"
        assert params["keywords"] == ["Python Developer"]
        assert params["location"] == ["United States"]
        assert params["f_TPR"] == ["r604800"]
        assert params["sortBy"] == ["DD"]
        if page > 1:
            assert params["start"] == [str((page - 1) * 25)]
    else:
        assert urlsplit(url).path == "/role/l/python-developer/united-states"
        if page > 1:
            assert params == {"page": [str(page)]}


@pytest.mark.parametrize("page", [0, -1, True, 1.5, "2", None])
def test_invalid_page_numbers(page):
    with pytest.raises(ValueError, match="positive integer"):
        build_paginated_search_url(JobSource.LINKEDIN, JobSearchRequest(keyword="Python"), page)


@pytest.mark.parametrize("source,url", [
    (JobSource.LINKEDIN, "https://www.linkedin.com/jobs/search/?keywords=C%2B%2B&x=1&x=2&empty=&start=99"),
    (JobSource.WELLFOUND, "https://wellfound.com/role/python-developer?x=1&x=2&empty=&page=99"),
])
def test_preserves_query_parameters(source, url):
    params = parse_qs(urlsplit(paginate_search_url(source, url, 2)).query, keep_blank_values=True)
    assert params["x"] == ["1", "2"]
    assert params["empty"] == [""]
    if source == JobSource.LINKEDIN:
        assert params["keywords"] == ["C++"]
        assert params["start"] == ["25"]
    else:
        assert params["page"] == ["2"]


@pytest.mark.parametrize("source,url", [
    (JobSource.WELLFOUND, "https://wellfound.com/jobs"),
    (JobSource.WELLFOUND, "https://wellfound.com/role/"),
    (JobSource.LINKEDIN, "https://www.linkedin.com/jobs/view/123/"),
    (JobSource.LINKEDIN, "https://linkedin.com.evil.example/jobs/search/"),
    (JobSource.WELLFOUND, "https://evil.example/role/python-developer"),
    (JobSource.LINKEDIN, "http://www.linkedin.com/jobs/search/"),
    (JobSource.LINKEDIN, "https://user@www.linkedin.com/jobs/search/"),
    (JobSource.LINKEDIN, "https://www.linkedin.com:8443/jobs/search/"),
    (JobSource.REALPYTHON_DEMO, "https://realpython.com/"),
])
def test_unsupported_pagination_contexts(source, url):
    with pytest.raises(ValueError):
        paginate_search_url(source, url, 1)


def test_unsupported_search_configurations():
    with pytest.raises(ValueError, match="Unsupported Wellfound role"):
        build_paginated_search_url(
            JobSource.WELLFOUND,
            JobSearchRequest(source="wellfound", keyword="Unknown Role"), 2,
        )
    with pytest.raises(ValueError, match="Unsupported Wellfound location"):
        build_paginated_search_url(
            JobSource.WELLFOUND,
            JobSearchRequest(source="wellfound", keyword="Python Developer", location="Unknown"), 2,
        )
    with pytest.raises(ValueError, match="source"):
        build_paginated_search_url(JobSource.WELLFOUND, JobSearchRequest(keyword="Python"), 2)
