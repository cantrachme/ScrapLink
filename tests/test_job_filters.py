from datetime import date, datetime, timedelta, timezone

import pytest

from backend.app.schemas.job import JobListing, JobSource
from backend.app.services.job_filters import matches_posting_window, parse_posting_date


NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


def job(**values):
    return JobListing(
        source=JobSource.LINKEDIN, job_url="https://www.linkedin.com/jobs/view/123/",
        title="Python Developer", company="Example", **values,
    )


@pytest.mark.parametrize("window,days", [("24h", 1), ("7d", 7), ("30d", 30)])
def test_exact_timestamp_windows(window, days):
    assert matches_posting_window(job(posted_at=NOW - timedelta(hours=2)), window, NOW)
    assert matches_posting_window(job(posted_at=NOW - timedelta(days=days)), window, NOW)
    assert not matches_posting_window(job(posted_at=NOW - timedelta(days=days, microseconds=1)), window, NOW)
    assert not matches_posting_window(job(posted_at=NOW + timedelta(seconds=1)), window, NOW)
    assert not matches_posting_window(job(), window, NOW)


@pytest.mark.parametrize("window,days", [("24h", 1), ("7d", 7), ("30d", 30)])
def test_date_only_boundaries(window, days):
    assert matches_posting_window(job(posted_date=NOW.date()), window, NOW)
    assert matches_posting_window(job(posted_date=(NOW - timedelta(days=days-1)).date()), window, NOW)
    assert not matches_posting_window(job(posted_date=(NOW - timedelta(days=days)).date()), window, NOW)
    assert not matches_posting_window(job(posted_date=date(2026, 10, 9)), window, NOW)
    midnight = NOW.replace(hour=0)
    assert matches_posting_window(job(posted_date=(midnight - timedelta(days=days)).date()), window, midnight)


def test_any_accepts_missing_and_old_dates_but_excludes_future():
    assert matches_posting_window(job(), "any", NOW)
    assert matches_posting_window(job(posted_date=date(2000, 1, 1)), "any", NOW)
    assert matches_posting_window(job(posted_at=NOW - timedelta(days=100)), "any", NOW)
    assert not matches_posting_window(job(posted_at=NOW + timedelta(hours=1)), "any", NOW)
    assert not matches_posting_window(job(posted_date=date(2026, 10, 9)), "any", NOW)


def test_timestamp_takes_precedence_over_date():
    assert not matches_posting_window(job(posted_at=NOW - timedelta(days=2), posted_date=NOW.date()), "24h", NOW)
    assert matches_posting_window(job(posted_at=NOW - timedelta(hours=2), posted_date=date(2000, 1, 1)), "24h", NOW)


def test_timezones_and_naive_timestamps_are_utc_consistent():
    timestamp = datetime.fromisoformat("2026-10-08T15:30:00+05:30")
    assert matches_posting_window(job(posted_at=timestamp), "24h", NOW)
    assert matches_posting_window(job(posted_at=timestamp), "24h", NOW.astimezone(timezone(timedelta(hours=-7))))
    assert matches_posting_window(job(posted_at=datetime(2026, 10, 8, 10)), "24h", NOW.replace(tzinfo=None))
    assert not matches_posting_window(job(posted_at=datetime.fromisoformat("2026-10-08T10:00:00-05:00")), "24h", NOW)


def test_unsupported_filter_raises():
    with pytest.raises(ValueError, match="Unsupported date_posted"):
        matches_posting_window(job(), "2d", NOW)


@pytest.mark.parametrize("raw,expected_date,expected_time", [
    ("2026-10-08", date(2026, 10, 8), None),
    ("20261008", date(2026, 10, 8), None),
    ("2026-W41-4", date(2026, 10, 8), None),
    ("2026-10-08T01:00:00+05:30", date(2026, 10, 7), datetime(2026, 10, 7, 19, 30, tzinfo=timezone.utc)),
    ("2026-10-08T12:00:00Z", NOW.date(), NOW),
    ("2026-10-08T12:00:00", NOW.date(), NOW),
    (None, None, None), ("yesterday", None, None), ("2026-10-08garbage", None, None),
])
def test_parse_dates_preserves_precision(raw, expected_date, expected_time):
    assert parse_posting_date(raw) == (expected_date, expected_time)
