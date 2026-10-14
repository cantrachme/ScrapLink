
from uuid import UUID

from sqlalchemy import case, cast, func, null
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Session

from backend.app.models.job import Job
from backend.app.schemas.job import JobListing
from backend.app.services.job_deduplication import normalize_job_url


class JobRepository:
    """PostgreSQL operations for extracted jobs."""

    @staticmethod
    def upsert(
        db: Session,
        listing: JobListing,
    ) -> Job:
        """
        Insert a new job or update an existing job.

        Identity: (source, job_url).

        Preserve previously collected information when a
        later extraction returns missing optional fields.

        Transaction commit is handled by the caller.
        """

        values = listing.model_dump(
            mode="python",
            exclude={"first_seen_at"},
        )

        # Convert enums into database string values.
        values["source"] = listing.source.value
        values["job_url"] = normalize_job_url(listing.source, listing.job_url)
        values["status"] = listing.status.value

        values["workplace_type"] = (
            listing.workplace_type.value
            if listing.workplace_type else None
        )

        values["employment_type"] = (
            listing.employment_type.value
            if listing.employment_type else None
        )

        values["compensation"] = (
            listing.compensation.model_dump(mode="json")
            if listing.compensation is not None
            else null()
        )

        stmt = insert(Job).values(**values)

        # Always refresh these when the job is rediscovered.
        updates = {
            "title": stmt.excluded.title,
            "company": func.coalesce(func.nullif(stmt.excluded.company, ""), Job.company),
            "updated_at": func.now(),
        }

        # Do not overwrite existing information with NULL.
        optional_fields = [
            "source_job_id",
            "application_url",
            "company_url",
            "location",
            "workplace_type",
            "employment_type",
            "seniority_level",
            "description",
            "experience_min_years",
            "experience_max_years",
            "posted_date",
            "posted_at",
            "posted_text",
            "last_verified_at",
        ]

        for field in optional_fields:
            updates[field] = func.coalesce(
                getattr(stmt.excluded, field),
                getattr(Job, field),
            )

        # Preserve existing compensation if the new
        # extraction does not provide compensation.
        if listing.compensation is not None:
            # Partial salary data must not erase previously known bounds,
            # currency or period. JSON nulls are missing data, not deletions.
            old_salary = case(
                (func.jsonb_typeof(Job.compensation) == "object", Job.compensation),
                else_=cast({}, JSONB),
            )
            new_salary = func.jsonb_strip_nulls(stmt.excluded.compensation)
            merged_salary = old_salary.op("||")(new_salary)
            incoming_salary = listing.compensation
            # A new bound can supersede a contradictory old bound. Never save
            # an invalid range that would make the job details API unreadable.
            if incoming_salary.min_amount is not None and incoming_salary.max_amount is None:
                merged_salary = case(
                    (Job.compensation["max_amount"].as_float() < incoming_salary.min_amount,
                     merged_salary.op("-")("max_amount")), else_=merged_salary,
                )
            if incoming_salary.max_amount is not None and incoming_salary.min_amount is None:
                merged_salary = case(
                    (Job.compensation["min_amount"].as_float() > incoming_salary.max_amount,
                     merged_salary.op("-")("min_amount")), else_=merged_salary,
                )
            for unit in ("currency", "period"):
                value = getattr(incoming_salary, unit)
                if value is not None:
                    merged_salary = case(
                        (Job.compensation[unit].as_string() != value,
                         old_salary.op("-")("min_amount").op("-")("max_amount")
                         .op("-")("raw_text").op("||")(new_salary)),
                        else_=merged_salary,
                    )
            updates["compensation"] = merged_salary

        # Do not overwrite existing lists with empty lists.
        for field in [
            "responsibilities",
            "requirements",
            "skills",
        ]:
            incoming = getattr(stmt.excluded, field)

            updates[field] = case(
                (
                    func.jsonb_array_length(incoming) > 0,
                    incoming,
                ),
                else_=getattr(Job, field),
            )

        # An unverified extraction must not erase an
        # existing verified job status.
        updates["status"] = case(
            (
                stmt.excluded.status == "unknown",
                Job.status,
            ),
            else_=stmt.excluded.status,
        )

        stmt = stmt.on_conflict_do_update(
            constraint="uq_jobs_source_url",
            set_=updates,
        )

        # Return the inserted or updated ORM object.
        statement = stmt.returning(Job)

        return db.scalars(
            statement,
            execution_options={"populate_existing": True},
        ).one()

    @staticmethod
    def get_by_id(
        db: Session,
        job_id: UUID,
    ) -> Job | None:
        """Retrieve a stored job by its database ID."""

        return db.get(Job, job_id)
