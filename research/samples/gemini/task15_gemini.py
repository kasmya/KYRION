"""
Task 15: Production-Grade Pydantic Payload Validation Service
Features: Custom input pattern validation, nested object relational mappings, detailed contextual error tracing.
Requires: fastapi, uvicorn, pydantic, email-validator
"""

import re
import uuid
from typing import List, Optional, Any
from datetime import datetime
import logging
from fastapi import FastAPI, HTTPException, status, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResultResponse, jsonify, JSONResponse
from pydantic import BaseModel, Field, EmailStr, field_validator, ValidationInfo

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Data Validation and Compliance Ingestion Gateway", version="1.0.0")

# --- Overriding Default Exception Interceptors to Format Clear Diagnostics ---
@app.exception_handler(RequestValidationError)
async def custom_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Formats validation errors into clear, machine-readable diagnostic messages."""
    error_diagnostics: List[Dict[str, Any]] = []
    for single_error in exc.errors():
        error_diagnostics.append({
            "field_location": " -> ".join([str(loc) for loc in single_error["loc"]]),
            "error_classification": single_error["type"],
            "diagnostic_message": single_error["msg"]
        })
    logger.warning(f"Inbound payload structure validation failure: {error_diagnostics}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"validation_status": "REJECTED", "structural_anomalies": error_diagnostics}
    )

# --- Pydantic Schema Architectures ---

class CommunicationContactSchema(BaseModel):
    """Validates structural identity mappings over telephone masks and formatting strings."""
    contact_type: str = Field(..., description="Label descriptor (e.g., corporate, fallback)")
    phone_number: str = Field(..., description="Target international dial string code line.")

    @field_validator('phone_number')
    @classmethod
    def verify_phone_number_format(cls, raw_phone_string: str) -> str:
        """Evaluates inbound telephone data against strict E.164 regular expressions."""
        clean_dial_line = raw_phone_string.strip()
        e164_pattern = r"^\+[1-9]\d{1,14}$"
        if not re.match(e164_pattern, clean_dial_line):
            raise ValueError("Phone numbers must be conforming structural strings tracking E.164 standard syntax formatting (e.g., +1234567890)")
        return clean_dial_line

class EnterpriseUserIngestionPayload(BaseModel):
    """Root model handling comprehensive identity verification routines."""
    transaction_id: str = Field(..., description="Unique transaction lookup identification string sequence token.")
    account_email: EmailStr = Field(..., description="Primary administrative point of contact email address coordinates.")
    account_tier_level: str = Field("standard", description="Access management groups classification levels mapping.")
    profile_score: float = Field(..., gt=0.0, le=100.0, description="Calculated analytics validation weight variables.")
    contact_channels: List[CommunicationContactSchema] = Field(..., description="Nested communication tracking numbers inventory array.")
    registered_timestamp: datetime = Field(default_factory=datetime.utcnow)

    @field_validator('transaction_id')
    @classmethod
    def verify_transaction_id_is_uuid(cls, input_token: str) -> str:
        """Asserts input token maps to a structurally valid UUID matrix pattern."""
        try:
            uuid.UUID(str(input_token))
            return input_token
        except ValueError:
            raise ValueError("Assigned 'transaction_id' must conform strictly to valid standard UUID character layout signatures.")

    @field_validator('account_tier_level')
    @classmethod
    def enforce_tier_allowlist(cls, target_tier: str) -> str:
        """Enforces a strict allowlist constraint for system security classification levels."""
        normalized_tier = target_tier.strip().lower()
        allowed_tiers = {"standard", "enterprise_vip", "system_auditor"}
        if normalized_tier not in allowed_tiers:
            raise ValueError(f"Value assignment rejected. Target tier variable choice must match options from: {allowed_tiers}")
        return normalized_tier

# --- REST Endpoint Handlers ---

@app.post("/validate_payload", status_code=status.HTTP_200_OK)
def ingest_and_verify_payload_data(validated_payload: EnterpriseUserIngestionPayload) -> Any:
    """Processes compliant payloads, outputting an acknowledgment token upon success."""
    logger.info(f"Successfully processed compliant transactional payload ID token reference: {validated_payload.transaction_id}")
    return {
        "validation_status": "COMPLIANT_SUCCESS",
        "processed_at": datetime.utcnow().isoformat(),
        "record_identifier": validated_payload.transaction_id
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
