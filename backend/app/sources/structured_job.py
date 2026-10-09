"""Shared schema.org JobPosting fields used by both source adapters."""

from backend.app.schemas.job import Compensation, EmploymentType, WorkplaceType


def employment_type(value):
    if not isinstance(value, str):
        return None

    normalized = value.strip().lower()
    normalized = normalized.replace("-", "_")
    normalized = normalized.replace(" ", "_")

    mapping = {
        "full_time": EmploymentType.FULL_TIME,
        "fulltime": EmploymentType.FULL_TIME,
        "part_time": EmploymentType.PART_TIME,
        "contract": EmploymentType.CONTRACT,
        "internship": EmploymentType.INTERNSHIP,
        "temporary": EmploymentType.TEMPORARY,
    }

    return mapping.get(normalized)


def workplace_type(value):
    if not isinstance(value, str):
        return None

    normalized = value.strip().lower()

    mapping = {
        "telecommute": WorkplaceType.REMOTE,
        "remote": WorkplaceType.REMOTE,
        "remote only": WorkplaceType.REMOTE,
        "in office": WorkplaceType.ONSITE,
        "onsite": WorkplaceType.ONSITE,
        "hybrid": WorkplaceType.HYBRID,
    }

    return mapping.get(normalized)


def compensation(data):
    salary = data.get("baseSalary")

    if not isinstance(salary, dict):
        return None

    value = salary.get("value", {})

    if isinstance(value, (int, float)):
        value = {
            "minValue": value,
            "maxValue": value,
        }

    if not isinstance(value, dict):
        return None

    period_map = {
        "HOUR": "hour",
        "MONTH": "month",
        "YEAR": "year",
    }

    period = period_map.get(
        str(value.get("unitText", "")).upper()
    )

    return Compensation(
        currency=salary.get("currency"),
        min_amount=value.get("minValue"),
        max_amount=value.get("maxValue"),
        period=period,
    )

