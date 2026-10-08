
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.models.job import Job
from backend.app.models.search import SearchTaskRecord
from backend.app.schemas.job import JobSource
from backend.app.services.job_executor import JobSearchExecutor


client = TestClient(app)
executor = JobSearchExecutor()


@pytest.fixture
def cleanup_records():
    search_ids = []
    job_urls = []

    yield search_ids, job_urls

    with SessionLocal.begin() as db:
        if search_ids:
            db.execute(
                delete(SearchTaskRecord).where(
                    SearchTaskRecord.search_id.in_(search_ids)
                )
            )

        if job_urls:
            db.execute(
                delete(Job).where(Job.job_url.in_(job_urls))
            )


def create_search(cleanup_records, source="linkedin"):
    response = client.post(
        "/api/v1/jobs/search",
        json={
            "keyword": "Python Developer",
            "source": source,
        },
    )

    assert response.status_code == 202

    search_id = response.json()["search_id"]
    cleanup_records[0].append(UUID(search_id))

    return search_id


def make_job_html():
    return """
    <html><head>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Python Developer",
        "description": "<p>Build Python APIs.</p>",
        "hiringOrganization": {
          "@type": "Organization",
          "name": "Example Company"
        }
      }
      </script>
    </head><body></body></html>
    """


def test_pending_search_has_empty_results(cleanup_records):
    search_id = create_search(cleanup_records)

    response = client.get(
        f"/api/v1/jobs/search/{search_id}/results"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["jobs"] == []
    assert response.json()["source"] == "linkedin"


def test_execute_search_and_retrieve_jobs(cleanup_records):
    search_id = create_search(cleanup_records)
    job_id = uuid4().int
    job_url = f"https://www.linkedin.com/jobs/view/{job_id}/"

    cleanup_records[1].append(job_url)

    executor.run_from_html(
        search_id=search_id,
        source=JobSource.LINKEDIN,
        listing_html=f'<a href="/jobs/view/{job_id}/">Job</a>',
        detail_pages={job_url: make_job_html()},
    )

    status_response = client.get(
        f"/api/v1/jobs/search/{search_id}"
    )

    assert status_response.json()["status"] == "completed"

    response = client.get(
        f"/api/v1/jobs/search/{search_id}/results"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total_discovered"] == 1
    assert data["total_extracted"] == 1
    assert data["total_failed"] == 0
    assert data["jobs"][0]["title"] == "Python Developer"
    assert data["jobs"][0]["source"] == "linkedin"
    assert "Build Python APIs" in data["jobs"][0]["description"]


def test_partial_failure_preserves_jobs(cleanup_records):
    search_id = create_search(cleanup_records, "wellfound")

    valid_id = uuid4().int
    missing_id = uuid4().int

    valid = f"https://wellfound.com/jobs/{valid_id}-valid"
    missing = f"https://wellfound.com/jobs/{missing_id}-missing"

    cleanup_records[1].append(valid)

    executor.run_from_html(
        search_id=search_id,
        source=JobSource.WELLFOUND,
        listing_html=f"""
        <a href="/jobs/{valid_id}-valid">First</a>
        <a href="/jobs/{missing_id}-missing">Second</a>
        """,
        detail_pages={valid: make_job_html()},
    )

    data = client.get(
        f"/api/v1/jobs/search/{search_id}/results"
    ).json()

    assert data["status"] == "completed"
    assert data["total_discovered"] == 2
    assert data["total_extracted"] == 1
    assert data["total_failed"] == 1
    assert data["failures"][0]["job_url"] == missing


def test_fatal_pipeline_failure(cleanup_records):
    search_id = create_search(cleanup_records)

    with pytest.raises(ValueError):
        executor.run_from_html(
            search_id=search_id,
            source=JobSource.LINKEDIN,
            listing_html=None,
            detail_pages={},
        )

    response = client.get(
        f"/api/v1/jobs/search/{search_id}"
    )

    assert response.json()["status"] == "failed"
    assert response.json()["error"] is not None


def test_search_persists_across_database_sessions(cleanup_records):
    search_id = create_search(cleanup_records)

    # Simulate reading the search in independent database
    # sessions, as happens after separate HTTP requests.
    with SessionLocal() as first_session:
        first = first_session.get(
            SearchTaskRecord,
            UUID(search_id),
        )

        assert first is not None
        assert first.status == "pending"

    with SessionLocal() as second_session:
        second = second_session.get(
            SearchTaskRecord,
            UUID(search_id),
        )

        assert second is not None
        assert second.search_id == UUID(search_id)
        assert second.request_payload["keyword"] == "Python Developer"
