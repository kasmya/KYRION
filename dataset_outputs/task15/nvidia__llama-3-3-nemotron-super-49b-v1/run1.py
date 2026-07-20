import json
from jsonschema import validate, ValidationError
from pydantic import BaseModel, validator, ValidationError as PydanticValidationError
from typing import Dict, List, Optional
import re

# Schema Definition for Pydantic Model
class JsonSchema(BaseModel):
    """Pydantic Model mirroring the expected JSON schema structure."""
    name: str
    email: str
    age: int
    phone: Optional[str]  # Optional for demonstration

    @validator('email')
    def email_validator(cls, v):
        """Validate email format using a simple regex pattern."""
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(pattern, v):
            raise ValueError("Invalid email format")
        return v

    @validator('phone', pre=True)
    def phone_validator(cls, v):
        """Validate phone number format (simple example, assumes a specific format)."""
        if v and not re.match(r"^\+\d{3}-\d{3}-\d{4}$", v):
            raise ValueError("Invalid phone number format. Expected: +XXX-XXX-XXXX")
        return v

# JSON Schema Definition for jsonschema Package
JSON_SCHEMA_DEFINITION = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "pattern": "^[a-zA-Z ]+$"},  # Only letters and spaces
        "email": {"type": "string", "format": "email"},
        "age": {"type": "integer", "minimum": 18},
        "phone": {"type": "string", "pattern": "^\\+\\d{3}-\\d{3}-\\d{4}$", "nullable": True}
    },
    "required": ["name", "email", "age"],
    "additionalProperties": False  # Ensure no extra properties are present
}

class DataValidationService:
    """Service for validating JSON data against a predefined schema."""
    
    def __init__(self, schema: Dict = JSON_SCHEMA_DEFINITION):
        """
        Initialize the validation service with a given schema.

        :param schema: JSON schema definition (default is JSON_SCHEMA_DEFINITION)
        """
        self.schema = schema

    def validate_with_jsonschema(self, data: Dict) -> bool:
        """
        Validate JSON data against the schema using jsonschema.

        :param data: JSON data to validate
        :return: True if valid, False otherwise
        :raises ValidationError: With detailed error message
        """
        try:
            validate(instance=data, schema=self.schema)
            return True
        except ValidationError as ve:
            print(f"JSONSchema Validation Error: {ve}")
            raise  # Re-raise after printing for external handling

    def validate_with_pydantic(self, data: Dict) -> JsonSchema:
        """
        Validate JSON data against the schema using Pydantic.

        :param data: JSON data to validate
        :return: Validated JsonSchema model if data is valid
        :raises PydanticValidationError: With detailed error message
        """
        try:
            return JsonSchema(**data)
        except PydanticValidationError as pve:
            print(f"Pydantic Validation Error: {pve}")
            raise  # Re-raise after printing for external handling

    def detailed_validation_report(self, data: Dict) -> Dict:
        """
        Generate a detailed report of validation errors using both libraries.

        :param data: JSON data to validate
        :return: Dictionary with validation results and error messages
        """
        report = {"valid": False, "errors": {}}
        
        # JSONSchema Validation
        try:
            self.validate_with_jsonschema(data)
            report["jsonschema"] = "Valid"
        except ValidationError as ve:
            report["jsonschema"] = "Invalid"
            report["errors"]["jsonschema"] = str(ve)
        
        # Pydantic Validation
        try:
            self.validate_with_pydantic(data)
            report["pydantic"] = "Valid"
            report["valid"] = True  # Overall valid if both pass, but here it's redundant
        except PydanticValidationError as pve:
            report["pydantic"] = "Invalid"
            report["errors"]["pydantic"] = str(pve)
        
        return report

# Example Usage
if __name__ == "__main__":
    validation_service = DataValidationService()
    
    # Valid Data
    valid_data = {
        "name": "John Doe",
        "email": "johndoe@example.com",
        "age": 30,
        "phone": "+123-456-7890"
    }
    print("Valid Data JSONSchema Validation:", validation_service.validate_with_jsonschema(valid_data))
    try:
        print("Valid Data Pydantic Validation:", validation_service.validate_with_pydantic(valid_data))
    except PydanticValidationError as e:
        print(e)
    
    # Invalid Data (Missing required field, wrong email format, incorrect age type)
    invalid_data = {
        "email": "invalid_email",  # Wrong format
        "age": "thirty",  # Wrong type
    }
    print("Invalid Data Validation Report:")
    print(validation_service.detailed_validation_report(invalid_data))