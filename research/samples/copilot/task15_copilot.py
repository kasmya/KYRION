"""
Data Validation Service using FastAPI and Pydantic.
Features:
- Validate JSON payloads against schemas
- Custom validators (email, phone, UUID)
- Generate OpenAPI documentation
- Detailed error messages
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr, validator
import re
import uuid

app = FastAPI(title="Data Validation Service")


class UserData(BaseModel):
    email: EmailStr
    phone: str
    user_id: str

    @validator("phone")
    def validate_phone(cls, v):
        if not re.match(r"^\+?\d{10,15}$", v):
            raise ValueError("Invalid phone number format")
        return v

    @validator("user_id")
    def validate_uuid(cls, v):
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError("Invalid UUID")
        return v


@app.post("/validate")
def validate(data: UserData):
    return {"msg": "Validation successful", "data": data.dict()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

