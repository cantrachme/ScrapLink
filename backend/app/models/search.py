
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class SearchTaskRecord(Base):
    __tablename__ = "search_tasks"

    search_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    source: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )

    request_payload: Mapped[dict] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        server_default="pending",
    )

    error: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    total_discovered: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )

    total_extracted: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )

    total_failed: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SearchTaskJob(Base):
    __tablename__ = "search_task_jobs"

    search_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "search_tasks.search_id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "jobs.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class ExtractionFailureRecord(Base):
    __tablename__ = "extraction_failures"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    search_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "search_tasks.search_id",
            ondelete="CASCADE",
        ),
    )

    source: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )

    job_url: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )

    error: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
