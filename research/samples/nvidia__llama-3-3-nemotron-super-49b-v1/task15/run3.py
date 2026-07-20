# Import necessary libraries
import json
from jsonschema import validate, ValidationError
from pydantic import BaseModel, Field, ValueError as PydanticValueError
from typing import Dict, Any

# Define a Pydantic model for schema (optional, for more robust type checking)
class SchemaModel(BaseModel):
    """Pydantic Model for Schema Definition"""
    type: str
    required: list[str] = Field(default_factory=list)
    properties: Dict[str, Dict[str, str]] = Field(default_factory=dict)

class ValidationService:
    """
    Data Validation Service using JSON Schema.

    Features:
    - Schema definition in JSON
    - Validation of required fields
    - Type checking
    - Pattern matching for string fields
    - Detailed error reporting

    """

    def __init__(self, schema: Dict[str, Any]):
        """
        Initialize the Validation Service with a JSON Schema.

        :param schema: JSON Schema dictionary
        """
        self.schema = schema
        # Optional: Validate schema against a meta-schema for added security
        self._validate_schema()

    def _validate_schema(self):
        """
        Validate the provided schema against a basic meta-schema.
        """
        meta_schema = {
            "type": "object",
            "required": ["type", "properties"],
            "properties": {
                "type": {"type": "string"},
                "properties": {"type": "object"},
                "required": {"type": "array", "items": {"type": "string"}}
            }
        }
        try:
            validate(instance=self.schema, schema=meta_schema)
        except ValidationError as e:
            raise ValueError("Invalid Schema") from e

    def validate_data(self, data: Dict[str, Any]) -> tuple[bool, list[str]]:
        """
        Validate JSON Data against the defined Schema.

        :param data: JSON Data to validate
        :return: Tuple of (is_valid, error_messages)
        """
        try:
            validate(instance=data, schema=self.schema)
            return True, []
        except ValidationError as e:
            # Extract and format error messages for user-friendly output
            error_messages = self._format_errors(e)
            return False, error_messages

    @staticmethod
    def _format_errors(error: ValidationError) -> list[str]:
        """
        Format ValidationError into a list of user-friendly error messages.

        :param error: ValidationError instance
        :return: List of error messages
        """
        errors = []
        if error.message:
            errors.append(f"Validation Error: {error.message}")
        for c in error.context:
            if c.message:
                errors.append(f"[{c.schema_id}] {c.message}")
        return errors

# Example Usage
if __name__ == "__main__":
    # Define a sample schema
    sample_schema = {
        "type": "object",
        "required": ["name", "email"],
        "properties": {
            "name": {"type": "string", "pattern": "^[A-Za-z ]+$"},
            "email": {"type": "string", "pattern": r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"},
            "age": {"type": "integer"}
        }
    }

    # Initialize the validation service
    validator = ValidationService(sample_schema)

    # Sample data to validate
    valid_data = {"name": "John Doe", "email": "johndoe@example.com", "age": 30}
    invalid_data = {"name": "Jane Doe", "email": "invalid_email"}  # Missing required field and invalid email

    # Validate data
    is_valid, errors = validator.validate_data(valid_data)
    print("Valid Data Validation Result:", is_valid, errors)

    is_valid, errors = validator.validate_data(invalid_data)
    print("Invalid Data Validation Result:", is_valid, errors)