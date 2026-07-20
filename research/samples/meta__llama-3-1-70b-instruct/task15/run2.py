import json
from jsonschema import validate, ValidationError, Draft7Validator
from typing import Any, Dict, List
from pydantic import BaseModel, ValidationError as PydanticValidationError

class ValidationService:
    def __init__(self, schema: Dict[str, Any]):
        """
        Initialize the validation service with a JSON schema.

        Args:
            schema (Dict[str, Any]): The JSON schema to use for validation.
        """
        self.schema = schema

    def validate(self, data: Dict[str, Any]) -> List[str]:
        """
        Validate JSON data against the defined schema.

        Args:
            data (Dict[str, Any]): The JSON data to validate.

        Returns:
            List[str]: A list of error messages. If the data is valid, an empty list is returned.
        """
        try:
            validate(instance=data, schema=self.schema, validator=Draft7Validator)
            return []
        except ValidationError as e:
            return [e.message]

    def validate_pydantic(self, data: Dict[str, Any]) -> List[str]:
        """
        Validate JSON data against the defined schema using Pydantic.

        Args:
            data (Dict[str, Any]): The JSON data to validate.

        Returns:
            List[str]: A list of error messages. If the data is valid, an empty list is returned.
        """
        try:
            class DynamicModel(BaseModel):
                class Config:
                    schema_extra = self.schema

            DynamicModel(**data)
            return []
        except PydanticValidationError as e:
            return [f"{error['loc'][0]}: {error['msg']}" for error in e.errors()]

def main():
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "pattern": "^[a-zA-Z]+$"},
            "age": {"type": "integer", "minimum": 0},
            "email": {"type": "string", "format": "email"}
        },
        "required": ["name", "age", "email"]
    }

    validation_service = ValidationService(schema)

    data = {
        "name": "John Doe",
        "age": 30,
        "email": "johndoe@example.com"
    }

    errors = validation_service.validate(data)
    if errors:
        print("Validation errors:")
        for error in errors:
            print(error)

    errors_pydantic = validation_service.validate_pydantic(data)
    if errors_pydantic:
        print("Pydantic validation errors:")
        for error in errors_pydantic:
            print(error)

if __name__ == "__main__":
    main()