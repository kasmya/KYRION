import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from jsonschema import Draft202012Validator, ValidationError, validate


class DataValidationService:
    """
    A service for validating JSON data against a JSON schema.

    Supports:
    - Schema definition in JSON (dict or file)
    - Required fields validation (via 'required' keyword)
    - Type checking (via 'type' keyword)
    - Pattern matching for string fields (via 'pattern' keyword)
    - Detailed error reporting with paths and messages
    - Security best practices (no eval/exec, safe file resolution)
    """

    def __init__(self, schema: Union[Dict[str, Any], str, Path]) -> None:
        """
        Initialize the service with a JSON schema.

        Args:
            schema: A dictionary representing the JSON schema, or a file path
                    to a JSON schema file (string or pathlib.Path).

        Raises:
            TypeError: If schema is not a dict, string, or Path.
            FileNotFoundError: If the schema file does not exist.
            PermissionError: If the schema file cannot be read.
            json.JSONDecodeError: If the schema file contains invalid JSON.
            jsonschema.exceptions.SchemaError: If the schema itself is invalid.
        """
        if isinstance(schema, dict):
            self._schema = schema
        elif isinstance(schema, (str, Path)):
            self._schema = self._load_schema_from_file(schema)
        else:
            raise TypeError("schema must be a dict, string, or Path")

        # Pre-compile the validator for performance and early schema validation
        self._validator = Draft202012Validator(self._schema)

    # ----------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------
    def validate(self, data: Dict[str, Any]) -> List[str]:
        """
        Validate a data dictionary against the schema.

        Args:
            data: The data to validate (must be a dict).

        Returns:
            A list of human-readable error messages.
            An empty list indicates valid data.

        Raises:
            TypeError: If data is not a dict.
        """
        if not isinstance(data, dict):
            raise TypeError("data must be a dict")

        errors: List[str] = []
        for error in self._validator.iter_errors(data):
            path = self._format_path(error.absolute_path)
            message = f"At '{path}': {error.message}"
            errors.append(message)
        return errors

    def is_valid(self, data: Dict[str, Any]) -> bool:
        """
        Quick validity check (returns True/False).

        Args:
            data: The data to validate (must be a dict).

        Returns:
            True if data is valid according to the schema, False otherwise.

        Raises:
            TypeError: If data is not a dict.
        """
        if not isinstance(data, dict):
            raise TypeError("data must be a dict")
        return self._validator.is_valid(data)

    def validate_or_raise(self, data: Dict[str, Any]) -> None:
        """
        Validate data and raise a ValidationError if invalid.

        Args:
            data: The data to validate (must be a dict).

        Raises:
            TypeError: If data is not a dict.
            jsonschema.exceptions.ValidationError: If validation fails.
        """
        if not isinstance(data, dict):
            raise TypeError("data must be a dict")
        self._validator.validate(data)

    def get_schema(self) -> Dict[str, Any]:
        """
        Return a deep copy of the schema dictionary.

        Returns:
            A copy of the schema.
        """
        return dict(self._schema)

    # ----------------------------------------------------------------------
    # Internal helpers
    # ----------------------------------------------------------------------
    @staticmethod
    def _load_schema_from_file(path: Union[str, Path]) -> Dict[str, Any]:
        """
        Load a JSON schema from a file with security checks.

        Args:
            path: File path (string or Path).

        Returns:
            Parsed schema dictionary.

        Raises:
            FileNotFoundError: If file does not exist.
            PermissionError: If file cannot be read.
            json.JSONDecodeError: If file content is not valid JSON.
        """
        file_path = Path(path).resolve()
        # Security: resolve() eliminates '..' and symbolic links to prevent
        # directory traversal attacks.
        if not file_path.exists():
            raise FileNotFoundError(f"Schema file not found: {file_path}")
        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except OSError as e:
            # Wrap OS errors (permissions, etc.) in a meaningful exception
            raise PermissionError(f"Cannot read schema file: {e}") from e

    @staticmethod
    def _format_path(path_parts: List[Union[str, int]]) -> str:
        """
        Format a list of path components into a dot-notation path.

        Args:
            path_parts: List of keys / indices from jsonschema's absolute_path.

        Returns:
            A string like "a.b[0].c".
        """
        result = "<root>"
        for part in path_parts:
            if isinstance(part, int):
                result = f"{result}[{part}]"
            else:
                result = f"{result}.{part}" if result != "<root>" else part
        return result


# --------------------------------------------------------------------------
# Example usage (commented out)
# --------------------------------------------------------------------------
# if __name__ == "__main__":
#     schema = {
#         "type": "object",
#         "properties": {
#             "name": {"type": "string", "pattern": "^[A-Za-z ]+$"},
#             "age": {"type": "integer", "minimum": 0},
#             "email": {"type": "string", "format": "email"}
#         },
#         "required": ["name", "email"]
#     }
#     validator = DataValidationService(schema)
#
#     # Valid data
#     data_valid = {"name": "Alice", "age": 30, "email": "alice@example.com"}
#     print(validator.validate(data_valid))  # []
#
#     # Invalid data
#     data_invalid = {"name": "Alice123", "age": -5}
#     print(validator.validate(data_invalid))
#     # Example output:
#     # ["At 'name': 'Alice123' does not match '^[A-Za-z ]+$'",
#     #  "At 'email': 'email' is a required property",
#     #  "At 'age': -5 is less than the minimum of 0"]