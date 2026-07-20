from pydantic import BaseModel, validator, ValidationError
from typing import Dict, Any
import json
from jsonschema import validate, ValidationError as JsonSchemaValidationError

class JsonSchema:
    """Represents a JSON Schema for validation."""
    def __init__(self, schema: Dict[str, Any]):
        """
        Initialize the JsonSchema with a schema dictionary.

        :param schema: JSON Schema dictionary
        """
        self.schema = schema

    def validate(self, data: Dict[str, Any]) -> None:
        """
        Validate the given data against the schema.

        :param data: Data to validate
        :raises JsonSchemaValidationError: If data does not match the schema
        """
        try:
            validate(instance=data, schema=self.schema)
        except JsonSchemaValidationError as e:
            raise ValidationFailure("JSON Schema Validation Failed", e) from e


class ValidationFailure(Exception):
    """Raised when validation fails."""
    def __init__(self, message: str, details: Any = None):
        """
        Initialize the ValidationFailure exception.

        :param message: Error message
        :param details: Additional error details
        """
        self.message = message
        self.details = details
        super().__init__(message)


class DataValidator:
    """Service for validating JSON data against a schema."""
    def __init__(self, schema: Dict[str, Any]):
        """
        Initialize the DataValidator with a JSON schema.

        :param schema: JSON Schema dictionary
        """
        self.schema = JsonSchema(schema)

    def validate_data(self, data: Dict[str, Any]) -> bool:
        """
        Validate the given data against the defined schema.

        :param data: Data to validate
        :return: True if valid, False otherwise
        :raises ValidationFailure: With detailed error message if validation fails
        """
        try:
            self.schema.validate(data)
            return True
        except ValidationFailure as e:
            raise e
        except Exception as e:
            raise ValidationFailure("Unexpected Validation Error", e) from e


# Example Usage
if __name__ == "__main__":
    example_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "pattern": "^[A-Za-z]+$"},
            "age": {"type": "integer", "minimum": 1}
        },
        "required": ["name", "age"]
    }

    validator_service = DataValidator(example_schema)

    valid_data = {"name": "John", "age": 30}
    invalid_data = {"name": "Jane123", "age": "twenty"}

    try:
        print(validator_service.validate_data(valid_data))  # Should print: True
        validator_service.validate_data(invalid_data)
    except ValidationFailure as e:
        print(f"Validation Failed: {e.message}")
        if e.details:
            print("Details:", e.details)