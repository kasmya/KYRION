from jsonschema import validate, ValidationError
from pydantic import BaseModel, ValidationError as PydanticValidationError
from typing import Any, Dict, List
import json

class DataValidationService:
    """
    A data validation service that validates JSON data against a defined schema.
    
    The service supports the following features:
    - Schema definition in JSON
    - Validation of required fields
    - Type checking
    - Pattern matching for string fields
    - Detailed error reporting
    """

    def __init__(self, schema: Dict[str, Any]):
        """
        Initializes the data validation service with a schema.
        
        Args:
        schema (Dict[str, Any]): The schema definition in JSON format.
        """
        self.schema = schema

    def validate_data(self, data: Dict[str, Any]) -> List[str]:
        """
        Validates the provided JSON data against the schema.
        
        Args:
        data (Dict[str, Any]): The JSON data to be validated.
        
        Returns:
        List[str]: A list of error messages if the data is invalid, otherwise an empty list.
        """
        try:
            validate(instance=data, schema=self.schema)
            return []
        except ValidationError as e:
            return [str(e)]

    def validate_data_with_pydantic(self, data: Dict[str, Any], model: BaseModel) -> List[str]:
        """
        Validates the provided JSON data against a Pydantic model.
        
        Args:
        data (Dict[str, Any]): The JSON data to be validated.
        model (BaseModel): The Pydantic model to validate against.
        
        Returns:
        List[str]: A list of error messages if the data is invalid, otherwise an empty list.
        """
        try:
            model.parse_obj(data)
            return []
        except PydanticValidationError as e:
            return [str(err) for err in e.errors()]

def main():
    # Define the schema
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "pattern": "^[a-zA-Z]+$"},
            "age": {"type": "integer", "minimum": 18}
        },
        "required": ["name", "age"]
    }

    # Create a data validation service
    service = DataValidationService(schema)

    # Validate some data
    data = {"name": "John", "age": 25}
    errors = service.validate_data(data)
    print(errors)

    # Define a Pydantic model
    class User(BaseModel):
        name: str
        age: int

    # Validate some data with Pydantic
    data = {"name": "Jane", "age": 30}
    errors = service.validate_data_with_pydantic(data, User)
    print(errors)

if __name__ == "__main__":
    main()