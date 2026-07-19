"""Data Validation Service with Pydantic, custom validators, and OpenAPI."""
import re, uuid
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr, field_validator, ValidationError

app = FastAPI(title="Validation Service", version="1.0.0")

class PhoneStr(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not re.match(r"^\+?1?\d{9,15}$", v):
            raise ValueError("Invalid phone number format")
        return cls(v)

class UserProfile(BaseModel):
    id: uuid.UUID
    email: EmailStr
    phone: PhoneStr
    age: int
    tags: List[str]
    website: Optional[str] = None

    @field_validator('age')
    @classmethod
    def check_age(cls, v: int) -> int:
        if not (18 <= v <= 120):
            raise ValueError('Age must be between 18 and 120')
        return v

    @field_validator('tags')
    @classmethod
    def check_tags(cls, v: List[str]) -> List[str]:
        if len(v) > 5:
            raise ValueError('Maximum 5 tags allowed')
        return [tag.lower().strip() for tag in v]

    @field_validator('website')
    @classmethod
    def check_website(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.startswith(('http://', 'https://')):
            raise ValueError('Website must start with http:// or https://')
        return v

@app.post("/validate", response_model=dict)
def validate_payload(profile: UserProfile):
    """Validate incoming JSON payload against schema."""
    try:
        # If we reach here, validation passed
        return {"status": "valid", "data": profile.model_dump()}
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())

@app.get("/")
def read_root():
    return {"message": "Validation Service API. Check /docs for OpenAPI schema."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)