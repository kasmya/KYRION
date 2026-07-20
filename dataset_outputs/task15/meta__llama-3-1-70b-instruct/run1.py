import json
from pydantic import BaseModel, ValidationError
from typing import Dict, List

class ValidationService:
    def __init__(self, schema: Dict):
        """
        Initialize the validation service with a schema.

        Args:
        schema (Dict): A JSON schema to validate against.
        """
        self.schema = schema

    def validate(self, data: Dict) -> Dict:
        """
        Validate JSON data against the defined schema.

        Args:
        data (Dict): JSON data to validate.

        Returns:
        Dict: A dictionary containing the validation result and errors (if any).

        Raises:
        Exception: If the schema or data is invalid.
        """
        try:
            # Use pydantic to validate the data
            class ValidationModel(BaseModel):
                class Config:
                    schema_extra = self.schema

            try:
                # Attempt to validate the data
                ValidationModel(**data)
                return {"valid": True, "errors": []}
            except ValidationError as e:
                # Handle validation errors
                errors = []
                for error in e.errors():
                    errors.append({"loc": error["loc"], "msg": error["msg"]})
                return {"valid": False, "errors": errors}

        except Exception as e:
            # Handle any other exceptions
            raise Exception("Failed to validate data: " + str(e))

def main():
    # Example usage
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "pattern": "^[a-zA-Z ]*$"},
            "age": {"type": "integer", "minimum": 18},
        },
        "required": ["name", "age"],
    }

    data = {
        "name": "John Doe",
        "age": 30,
    }

    validation_service = ValidationService(schema)
    result = validation_service.validate(data)
    print(json.dumps(result, indent=4))

    # Test with invalid data
    data = {
        "name": "John Doe",
        "age": "thirty",  # Invalid age
    }

    result = validation_service.validate(data)
    print(json.dumps(result, indent=4))

if __name__ == "__main__":
    main()