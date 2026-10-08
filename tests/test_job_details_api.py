"""Stored-job read contracts, isolated in PostgreSQL rollback transactions."""
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.database import engine, get_db
from backend.app.main import app
from backend.app.repositories.job_repository import JobRepository
from backend.app.repositories.search_repository import SearchRepository
from backend.app.schemas.job import Compensation, JobListing, JobSearchRequest, JobSource
from backend.app.services.job_pipeline import PipelineResult


@pytest.fixture
def stored_api():
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                def override_db():
                    yield session
                app.dependency_overrides[get_db] = override_db
                try:
                    with TestClient(app) as client:
                        yield session, client
                finally:
                    app.dependency_overrides.pop(get_db, None)
        finally:
            transaction.rollback()


def listing(**overrides):
    values = dict(source=JobSource.LINKEDIN,
                  job_url=f"https://www.linkedin.com/jobs/view/{uuid4().int}/",
                  title="Engineer", company="Example")
    return JobListing(**(values | overrides))


def complete_search(db, job):
    task = SearchRepository.create(db, JobSearchRequest(keyword="Engineer"), JobSource.LINKEDIN)
    SearchRepository.start(db, task.search_id)
    SearchRepository.complete(db, task.search_id, PipelineResult(
        source=JobSource.LINKEDIN, discovered_urls=[job.job_url], jobs=[job]))
    return task.search_id


def test_get_persisted_job_preserves_complete_structured_fields(stored_api):
    db, client = stored_api
    description = '<p>Build APIs &amp; services.</p>\n' + ('Full paragraph.\n\n' * 2000) + 'Final paragraph.'
    job = listing(description=description, source_job_id="platform-123",
                  application_url="https://example.com/apply", company_url="https://example.com",
                  location="London", workplace_type="hybrid", employment_type="contract",
                  seniority_level="Senior", responsibilities=["Build"], requirements=["Experience"],
                  skills=["Python"], experience_min_years=0, experience_max_years=5,
                  compensation=Compensation(currency="GBP", min_amount=50, max_amount=75, period="hour"),
                  posted_date=date(2026, 10, 7), posted_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
                  posted_text="Yesterday", status="active", last_verified_at=datetime.now(timezone.utc))
    stored = JobRepository.upsert(db, job)
    response = client.get(f"/api/v1/jobs/{stored.id}")
    assert response.status_code == 200
    data = response.json()
    assert UUID(data["id"]) == stored.id
    assert data["description"] == description
    expected = job.model_dump(mode="json", exclude={"first_seen_at"})
    assert {key: data[key] for key in expected} == expected
    assert data["first_seen_at"] and data["updated_at"]
    assert set(data) == set(JobListing.model_fields) | {"id", "updated_at"}


def test_get_job_serializes_nulls_and_empty_lists(stored_api):
    db, client = stored_api
    stored = JobRepository.upsert(db, listing())
    data = client.get(f"/api/v1/jobs/{stored.id}").json()
    for key in ("description", "compensation", "posted_at", "posted_date", "workplace_type", "employment_type", "application_url", "last_verified_at"):
        assert data[key] is None
    assert data["skills"] == data["responsibilities"] == data["requirements"] == []


def test_job_not_found(stored_api):
    _, client = stored_api
    response = client.get(f"/api/v1/jobs/{uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found"}


def test_invalid_job_uuid(stored_api, monkeypatch):
    _, client = stored_api
    def unexpected_lookup(*args):
        pytest.fail("Invalid UUID reached the repository")
    monkeypatch.setattr(JobRepository, "get_by_id", unexpected_lookup)
    assert client.get("/api/v1/jobs/not-a-uuid").status_code == 422


def test_search_results_ids_match_single_job_and_other_searches(stored_api):
    db, client = stored_api
    job = listing(description="Full stored description.\n\nLast paragraph.", skills=["Python"])
    first = complete_search(db, job)
    second = complete_search(db, job)
    first_results = client.get(f"/api/v1/jobs/search/{first}/results").json()
    second_results = client.get(f"/api/v1/jobs/search/{second}/results").json()
    a, b = first_results["jobs"][0], second_results["jobs"][0]
    assert a["id"] == b["id"]
    assert JobRepository.get_by_id(db, UUID(a["id"])) is not None
    assert client.get(f'/api/v1/jobs/{a["id"]}').json() == a
    assert a["description"] == job.description
    assert first_results["search_id"] == str(first)
    assert first_results["source"] == "linkedin"
    assert first_results["discovered_urls"] == [job.job_url]
    assert first_results["failures"] == []
    assert first_results["total_discovered"] == first_results["total_extracted"] == 1
    assert first_results["total_failed"] == 0


def test_search_routes_remain_compatible(stored_api):
    _, client = stored_api
    response = client.post("/api/v1/jobs/search", json={"keyword": "Python"})
    assert response.status_code == 202
    search_id = response.json()["search_id"]
    assert client.get(f"/api/v1/jobs/search/{search_id}").json()["status"] == "pending"
    results = client.get(f"/api/v1/jobs/search/{search_id}/results")
    assert results.status_code == 200
    assert results.json()["jobs"] == []
    assert results.json()["status"] == "pending"


def test_extraction_input_still_requires_no_database_identity():
    job = listing()
    assert "id" not in job.model_dump()
    assert "updated_at" not in job.model_dump()
