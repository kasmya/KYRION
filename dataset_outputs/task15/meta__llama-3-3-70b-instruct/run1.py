from jsonschema import validate, ValidationError
from typing import Dict, Any
import json

class DataValidationService:
    """
    A service for validating JSON data against a defined schema.
    
    Attributes:
    schema (Dict[str, Any]): The JSON schema to validate against.
    """

    def __init__(self, schema: Dict[str, Any]):
        """
        Initializes the DataValidationService with a JSON schema.
        
        Args:
        schema (Dict[str, Any]): The JSON schema to validate against.
        """
        self.schema = schema

    def validate_data(self, data: Dict[str, Any]) -> None:
        """
        Validates JSON data against the defined schema.
        
        Args:
        data (Dict[str, Any]): The JSON data to validate.
        
        Raises:
        ValidationError: If the data is invalid.
        """
        try:
            validate(instance=data, schema=self.schema)
        except ValidationError as e:
            raise ValueError(f"Invalid data: {e}")

    def validate_required_fields(self, data: Dict[str, Any]) -> None:
        """
        Validates that all required fields are present in the data.
        
        Args:
        data (Dict[str, Any]): The JSON data to validate.
        
        Raises:
        ValueError: If a required field is missing.
        """
        required_fields = [field for field, props in self.schema.get("properties", {}).items() if props.get("required", False)]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

    def validate_types(self, data: Dict[str, Any]) -> None:
        """
        Validates the types of the data against the schema.
        
        Args:
        data (Dict[str, Any]): The JSON data to validate.
        
        Raises:
        ValueError: If a type mismatch is found.
        """
        for field, value in data.items():
            props = self.schema.get("properties", {}).get(field, {})
            type_ = props.get("type")
            if type_ == "string" and not isinstance(value, str):
                raise ValueError(f"Type mismatch for field {field}: expected string, got {type(value).__name__}")
            elif type_ == "integer" and not isinstance(value, int):
                raise ValueError(f"Type mismatch for field {field}: expected integer, got {type(value).__name__}")
            elif type_ == "number" and not isinstance(value, (int, float)):
                raise ValueError(f"Type mismatch for field {field}: expected number, got {type(value).__name__}")

    def validate_patterns(self, data: Dict[str, Any]) -> None:
        """
        Validates string fields against pattern constraints.
        
        Args:
        data (Dict[str, Any]): The JSON data to validate.
        
        Raises:
        ValueError: If a pattern mismatch is found.
        """
        for field, value in data.items():
            props = self.schema.get("properties", {}).get(field, {})
            pattern = props.get("pattern")
            if pattern and not isinstance(value, str):
                raise ValueError(f"Pattern validation only applies to strings, but field {field} is of type {type(value).__name__}")
            elif pattern and not self._match_pattern(value, pattern):
                raise ValueError(f"Pattern mismatch for field {field}: {value} does not match {pattern}")

    @staticmethod
    def _match_pattern(value: str, pattern: str) -> bool:
        """
        Checks if a string matches a pattern.
        
        Args:
        value (str): The string to check.
        pattern (str): The pattern to match against.
        
        Returns:
        bool: True if the string matches the pattern, False otherwise.
        """
        import re
        return bool(re.match(pattern, value))

# Example usage
if __name__ == "__main__":
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "required": True, "pattern": "^[a-zA-Z]+$"},
            "age": {"type": "integer", "required": True},
        },
        "required": ["name", "age"]
    }
    data = {
        "name": "John",
        "age": 30
    }
    service = DataValidationService(schema)
    service.validate_data(data)
    service.validate_required_fields(data)
    service.validate_types(data)
    service.validate_patterns(data)
    print("Data is valid")