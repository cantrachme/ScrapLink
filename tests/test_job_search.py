
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas.job import JobSearchRequest
from backend.app.services.task_manager import (
    SearchTaskManager,
    TaskStatus,
)

client = TestClient(app)


def test_create_search_task():
    response = client.post(
        "/api/v1/jobs/search",
        json={
            "keyword": "Python Developer",
            "location": "United States",
            "date_posted": "24h",
            "max_results": 50,
        },
    )

    assert response.status_code == 202

    data = response.json()
    assert data["search_id"]
    assert data["status"] == "pending"


def test_retrieve_search_task():
    create_response = client.post(
        "/api/v1/jobs/search",
        json={"keyword": "Software Engineer"},
    )

    search_id = create_response.json()["search_id"]

    response = client.get(
        f"/api/v1/jobs/search/{search_id}"
    )

    assert response.status_code == 200
    assert response.json()["search_id"] == search_id
    assert response.json()["request"]["keyword"] == "Software Engineer"


def test_unknown_search_returns_404():
    response = client.get(
        f"/api/v1/jobs/search/{uuid4()}"
    )

    assert response.status_code == 404


def test_empty_keyword_returns_422():
    response = client.post(
        "/api/v1/jobs/search",
        json={"keyword": "   "},
    )

    assert response.status_code == 422


def test_task_status_updates():
    manager = SearchTaskManager()
    task = manager.create_task(
        JobSearchRequest(keyword="AI Engineer")
    )

    updated = manager.update_status(
        task.search_id,
        TaskStatus.RUNNING,
    )

    assert updated is not None
    assert updated.status == TaskStatus.RUNNING
    assert manager.get_task(task.search_id).status == TaskStatus.RUNNING
