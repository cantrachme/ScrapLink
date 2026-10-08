
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from backend.app.models import (
    Base,
    Job,
    SearchTaskRecord,
    SearchTaskJob,
    ExtractionFailureRecord,
)


def test_database_tables_registered():
    expected = {
        "jobs",
        "search_tasks",
        "search_task_jobs",
        "extraction_failures",
        "search_events",
    }

    assert set(Base.metadata.tables.keys()) == expected


def test_job_columns():
    columns = Job.__table__.columns.keys()

    assert "title" in columns
    assert "company" in columns
    assert "description" in columns
    assert "posted_date" in columns
    assert "skills" in columns
    assert "compensation" in columns

    assert isinstance(
        Job.__table__.c.skills.type,
        JSONB,
    )

    unique_constraints = [
        constraint
        for constraint in Job.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    assert any(
        {column.name for column in constraint.columns}
        == {"source", "job_url"}
        for constraint in unique_constraints
    )


def test_search_task_columns():
    columns = SearchTaskRecord.__table__.columns.keys()

    assert "search_id" in columns
    assert "request_payload" in columns
    assert "status" in columns
    assert "total_discovered" in columns
    assert "total_extracted" in columns
    assert "total_failed" in columns


def test_foreign_keys():
    association_fks = {
        fk.target_fullname
        for fk in SearchTaskJob.__table__.foreign_keys
    }

    assert "jobs.id" in association_fks
    assert "search_tasks.search_id" in association_fks

    failure_fks = {
        fk.target_fullname
        for fk in ExtractionFailureRecord.__table__.foreign_keys
    }

    assert "search_tasks.search_id" in failure_fks
