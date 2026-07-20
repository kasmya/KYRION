import json
from pydantic import BaseModel, ValidationError
from typing import Any, Dict

class ValidationErrorDetail(BaseModel):
    """Detailed validation error information."""
    loc: list[str]
    msg: str
    type: str

class ValidationResult(BaseModel):
    """Validation result."""
    valid: bool
    errors: list[ValidationErrorDetail] | None

class DataValidationService:
    """Data validation service using Pydantic."""
    
    def __init__(self, schema: Dict[str, Any]):
        """Initialize the data validation service with a schema.
        
        Args:
        schema (Dict[str, Any]): The schema definition in JSON.
        """
        self.schema = schema
    
    def validate(self, data: Dict[str, Any]) -> ValidationResult:
        """Validate JSON data against the defined schema.
        
        Args:
        data (Dict[str, Any]): The JSON data to be validated.
        
        Returns:
        ValidationResult: The validation result, including detailed error information if validation fails.
        """
        try:
            # Attempt to create a Pydantic model instance from the data
            _ = self._create_model_instance(self.schema, data)
            return ValidationResult(valid=True)
        except ValidationError as e:
            # If validation fails, extract and format error information
            errors = [
                ValidationErrorDetail(
                    loc=path,
                    msg=error["msg"],
                    type=error["type"],
                )
                for path, error in e.errors()
            ]
            return ValidationResult(valid=False, errors=errors)
    
    @staticmethod
    def _create_model_instance(schema: Dict[str, Any], data: Dict[str, Any]) -> BaseModel:
        """Create a Pydantic model instance from the schema and data.
        
        Args:
        schema (Dict[str, Any]): The schema definition in JSON.
        data (Dict[str, Any]): The JSON data to be validated.
        
        Returns:
        BaseModel: The Pydantic model instance.
        """
        # Create a Pydantic model class dynamically from the schema
        model_class = json.loads(
            json.dumps(schema), object_hook=lambda d: {"__root__": d}
        )
        model_class = pydantic.create_model("DynamicModel", **model_class)
        # Create a Pydantic model instance from the data
        return model_class.parse_obj(data)

# Example usage
if __name__ == "__main__":
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "pattern": "^John$"},
            "age": {"type": "integer", "minimum": 18},
        },
        "required": ["name", "age"],
    }
    data = {"name": "John", "age": 30}
    service = DataValidationService(schema)
    result = service.validate(data)
    print(result)