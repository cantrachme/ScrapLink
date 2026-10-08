"""Posting-date verification with explicit UTC and date-only semantics."""

from datetime import date, datetime, time, timedelta, timezone

from backend.app.schemas.job import JobListing


def _as_utc(value: datetime) -> datetime:
    # Naive source timestamps and test clocks are consistently interpreted as UTC.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_posting_date(value: object) -> tuple[date | None, datetime | None]:
    """Preserve ISO timestamp precision; never promote a date to midnight."""
    if not isinstance(value, str):
        return None, None
    value = value.strip()
    try:
        return date.fromisoformat(value), None
    except ValueError:
        pass
    try:
        timestamp = _as_utc(datetime.fromisoformat(value))
        return timestamp.date(), timestamp
    except ValueError:
        return None, None


def matches_posting_window(
    job: JobListing,
    date_posted: str,
    now: datetime | None = None,
) -> bool:
    """Verify an inclusive posting window against one fixed reference time.

    For date-only values, the whole day's *possible past* must fit the window.
    Today's interval ends at now, so today qualifies, as required, while a
    partially overlapping lower-bound date does not. Future days never qualify.
    'any' also rejects known future dates, but accepts missing dates.
    """
    windows = {"24h": timedelta(days=1), "7d": timedelta(days=7), "30d": timedelta(days=30)}
    if date_posted != "any" and date_posted not in windows:
        raise ValueError(f"Unsupported date_posted filter: {date_posted}")
    reference = _as_utc(now or datetime.now(timezone.utc))
    lower = reference - windows[date_posted] if date_posted != "any" else None
    if job.posted_at is not None:
        timestamp = _as_utc(job.posted_at)
        return timestamp <= reference and (lower is None or timestamp >= lower)
    if job.posted_date is not None:
        start = datetime.combine(job.posted_date, time.min, tzinfo=timezone.utc)
        return start <= reference and (lower is None or start >= lower)
    return date_posted == "any"
