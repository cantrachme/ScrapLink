
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas.job import JobSource
from backend.app.services.job_executor import (
    JobSearchExecutor,
)
from backend.app.services.task_manager import task_manager


client = TestClient(app)
executor = JobSearchExecutor(task_manager)


def create_search():
    response = client.post(
        "/api/v1/jobs/search",
        json={"keyword": "Python Developer"},
    )
    assert response.status_code == 202
    return response.json()["search_id"]


def make_job_html():
    return """
    <html>
      <head>
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
      </head>
    </html>
    """


def test_pending_search_has_empty_results():
    search_id = create_search()

    response = client.get(
        f"/api/v1/jobs/search/{search_id}/results"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["jobs"] == []


def test_execute_search_and_retrieve_jobs():
    search_id = create_search()
    job_url = "https://www.linkedin.com/jobs/view/12345/"

    executor.run_from_html(
        search_id=search_id,
        source=JobSource.LINKEDIN,
        listing_html='<a href="/jobs/view/12345/">Job</a>',
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


def test_partial_failure_preserves_jobs():
    search_id = create_search()

    valid = "https://wellfound.com/jobs/12345-valid"
    missing = "https://wellfound.com/jobs/67890-missing"

    executor.run_from_html(
        search_id=search_id,
        source=JobSource.WELLFOUND,
        listing_html="""
        <a href="/jobs/12345-valid">First</a>
        <a href="/jobs/67890-missing">Second</a>
        """,
        detail_pages={
            valid: make_job_html(),
        },
    )

    response = client.get(
        f"/api/v1/jobs/search/{search_id}/results"
    )

    data = response.json()

    assert data["status"] == "completed"
    assert data["total_discovered"] == 2
    assert data["total_extracted"] == 1
    assert data["total_failed"] == 1
    assert data["failures"][0]["job_url"] == missing


def test_fatal_pipeline_failure():
    search_id = create_search()

    with pytest.raises(ValueError):
        executor.run_from_html(
            search_id=search_id,
            source=JobSource.REALPYTHON_DEMO,
            listing_html="<html></html>",
            detail_pages={},
        )

    response = client.get(
        f"/api/v1/jobs/search/{search_id}"
    )

    assert response.json()["status"] == "failed"
    assert "Unsupported job source" in response.json()["error"]
