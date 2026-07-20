from pydantic import BaseModel, ValidationError
from typing import Dict, Any
import json

class DataValidationService:
    """
    A data validation service that validates JSON data against a defined schema.
    
    The service supports schema definition in JSON, validation of required fields, 
    type checking, pattern matching for string fields, and detailed error reporting.
    """

    def __init__(self, schema: Dict[str, Any]):
        """
        Initializes the data validation service with a given schema.
        
        Args:
        - schema (Dict[str, Any]): The JSON schema to validate against.
        """
        self.schema = schema

    def validate(self, data: Dict[str, Any]) -> bool:
        """
        Validates the given JSON data against the schema.
        
        Args:
        - data (Dict[str, Any]): The JSON data to validate.
        
        Returns:
        - bool: True if the data is valid, False otherwise.
        """
        try:
            # Use pydantic to create a model from the schema
            model = self._create_model(self.schema)
            # Validate the data using the model
            model(**data)
            return True
        except ValidationError as e:
            # Handle validation errors and return False
            self._handle_error(e)
            return False

    def _create_model(self, schema: Dict[str, Any]) -> BaseModel:
        """
        Creates a pydantic model from the given schema.
        
        Args:
        - schema (Dict[str, Any]): The JSON schema to create a model from.
        
        Returns:
        - BaseModel: The created pydantic model.
        """
        # Create a model using the schema
        model = json.loads(json.dumps(schema))
        # Convert the model to a pydantic model
        return BaseModel(**model)

    def _handle_error(self, error: ValidationError) -> None:
        """
        Handles validation errors and prints detailed error messages.
        
        Args:
        - error (ValidationError): The validation error to handle.
        """
        # Get the error messages
        error_messages = error.errors()
        # Print the error messages
        for error_message in error_messages:
            print(f"Error: {error_message['msg']} at {error_message['loc']}")

# Example usage
if __name__ == "__main__":
    # Define a schema
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
    data = {"name": "John", "age": 30}
    if service.validate(data):
        print("Data is valid")
    else:
        print("Data is invalid")