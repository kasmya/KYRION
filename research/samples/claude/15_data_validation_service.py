"""
### Task 15: Data Validation Service (Pydantic + FastAPI)

A REST service that validates JSON payloads against strict schemas with
custom validators (email, phone, UUID) and returns detailed, field-level
error messages. OpenAPI docs are generated automatically by FastAPI at
/docs and /redoc.

Requirements:
    pip install fastapi "uvicorn[standard]" pydantic email-validator

Run:
    uvicorn 15_data_validation_service:app --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import List, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("data_validation_service")

PHONE_REGEX = re.compile(r"^\+?[1-9]\d{7,14}$")  # loose E.164-style validation


class ContactRecord(BaseModel):
    """Schema representing a single contact record to validate.

    Attributes:
        full_name: The contact's full name (2-100 characters).
        email: A valid email address.
        phone: A phone number in a loose E.164-like format.
        external_id: A UUID identifying this record in an external system.
        tags: Optional list of free-form tags.
    """

    full_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone: str
    external_id: str
    tags: Optional[List[str]] = Field(default_factory=list)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        """Ensures the phone number matches a loose E.164-style pattern."""
        if not PHONE_REGEX.match(value):
            raise ValueError(
                "phone must be in E.164-like format, e.g. '+14155552671', with 8-15 digits"
            )
        return value

    @field_validator("external_id")
    @classmethod
    def validate_external_id(cls, value: str) -> str:
        """Ensures external_id is a syntactically valid UUID (any version)."""
        try:
            uuid.UUID(value)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError(f"external_id must be a valid UUID string: {exc}") from exc
        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        """Ensures tags are non-empty, lowercase, alphanumeric-ish strings."""
        if value is None:
            return value
        cleaned = []
        for tag in value:
            tag = tag.strip().lower()
            if not tag:
                raise ValueError("tags must not contain empty strings")
            if not re.match(r"^[a-z0-9_-]+$", tag):
                raise ValueError(
                    f"tag '{tag}' contains invalid characters; only a-z, 0-9, '_' and '-' allowed"
                )
            cleaned.append(tag)
        return cleaned


class ValidationSuccessResponse(BaseModel):
    """Response returned when a payload passes validation."""

    valid: bool = True
    record: ContactRecord


class FieldError(BaseModel):
    """A single field-level validation error."""

    field: str
    message: str
    input_value: Optional[str] = None


class ValidationErrorResponse(BaseModel):
    """Response returned when a payload fails validation."""

    valid: bool = False
    errors: List[FieldError]


app = FastAPI(
    title="Data Validation Service",
    description="Validates structured JSON payloads with detailed, field-level error reporting.",
    version="1.0.0",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Converts FastAPI/Pydantic validation errors into a clean, structured response."""
    errors: List[dict] = []
    for error in exc.errors():
        field_path = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        errors.append(
            {
                "field": field_path or "<root>",
                "message": error["msg"],
                "input_value": str(error.get("input")),
            }
        )
    logger.info("Validation failed with %d error(s) on %s", len(errors), request.url.path)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"valid": False, "errors": errors},
    )


@app.post(
    "/validate/contact",
    response_model=ValidationSuccessResponse,
    responses={422: {"model": ValidationErrorResponse}},
    summary="Validate a single contact record",
)
async def validate_contact(record: ContactRecord) -> ValidationSuccessResponse:
    """Validates a contact record payload and echoes it back if valid."""
    logger.info("Successfully validated contact record for '%s'", record.email)
    return ValidationSuccessResponse(record=record)


@app.post(
    "/validate/contacts/batch",
    summary="Validate a batch of contact records, reporting per-item errors",
)
async def validate_contacts_batch(records: List[dict]) -> dict:
    """Validates a batch of raw dicts individually so one bad record doesn't fail the batch."""
    results = []
    for index, raw_record in enumerate(records):
        try:
            validated = ContactRecord(**raw_record)
            results.append({"index": index, "valid": True, "record": validated.model_dump()})
        except Exception as exc:  # noqa: BLE001 - pydantic ValidationError and friends
            results.append({"index": index, "valid": False, "error": str(exc)})

    valid_count = sum(1 for r in results if r["valid"])
    logger.info("Batch validation: %d/%d records valid", valid_count, len(records))
    return {"total": len(records), "valid_count": valid_count, "results": results}


@app.get("/health", summary="Health check endpoint")
async def health() -> dict:
    """Simple liveness probe."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
