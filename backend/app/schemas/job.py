
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class DatePosted(str, Enum):
    PAST_24_HOURS = "24h"
    PAST_WEEK = "7d"
    PAST_MONTH = "30d"


class JobSearchRequest(BaseModel):
    keyword: str = Field(
        min_length=1,
        max_length=200,
        description="Job title or search keywords",
    )

    location: str = Field(
        default="United States",
        max_length=200,
    )

    date_posted: DatePosted = DatePosted.PAST_24_HOURS

    max_results: int = Field(
        default=50,
        ge=1,
        le=500,
    )

    @field_validator("keyword", "location")
    @classmethod
    def strip_whitespace(cls, value: str) -> str:
        return value.strip()

    @field_validator("keyword")
    @classmethod
    def validate_keyword(cls, value: str) -> str:
        if not value:
            raise ValueError("Keyword cannot be empty")
        return value


class JobSearchResponse(BaseModel):
    search_id: str
    status: str
    message: str
