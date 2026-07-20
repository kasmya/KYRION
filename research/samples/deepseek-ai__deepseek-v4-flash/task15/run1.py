import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import jsonschema
from jsonschema import ValidationError, validate

logger = logging.getLogger(__name__)


class DataValidationService:
    """
    A service for validating JSON data against a JSON Schema.

    Features:
    - Schema definition in JSON (dictionary or file path)
    - Validation of required fields, type checking, and pattern matching
    - Detailed error reporting with paths, messages, and error types
    - Comprehensive error handling and security best practices
    """

    def __init__(self, schema: Union[Dict[str, Any], str, Path]) -> None:
        """
        Initialize the service with a JSON Schema.

        Args:
            schema: Schema as a dictionary, or file path (string or Path) to a JSON file
                     containing the schema.

        Raises:
            TypeError: If schema is neither a dict nor a valid file path.
            ValueError: If the schema file cannot be read or parsed.
            jsonschema.exceptions.SchemaError: If the schema itself is invalid.
        """
        if isinstance(schema, (dict,)):
            self._schema = schema
        elif isinstance(schema, (str, Path)):
            self._schema = self._load_schema_from_file(schema)
        else:
            raise TypeError(
                "Schema must be a dictionary or a file path (string or Path)."
                f" Got {type(schema).__name__}."
            )

        # Validate the schema itself to ensure it's a valid JSON Schema
        # This catches malformed schemas early and provides clear errors.
        try:
            jsonschema.Draft7Validator.check_schema(self._schema)
        except jsonschema.SchemaError as e:
            logger.error("Invalid schema provided: %s", e)
            raise

    @staticmethod
    def _load_schema_from_file(path: Union[str, Path]) -> Dict[str, Any]:
        """
        Load a JSON Schema from a file.

        Args:
            path: Path to the schema file.

        Returns:
            The schema as a dictionary.

        Raises:
            FileNotFoundError: If the file does not exist.
            json.JSONDecodeError: If the file contains invalid JSON.
            ValueError: If the parsed content is not a dictionary.
        """
        file_path = Path(path).resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"Schema file not found: {file_path}")
        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in schema file: {e}") from e

        if not isinstance(content, dict):
            raise ValueError("Schema file must contain a JSON object (dictionary).")

        return content

    def validate(self, data: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Validate the given data against the schema.

        Args:
            data: The JSON data to validate (as a dictionary).

        Returns:
            A tuple (is_valid, errors):
            - is_valid: True if data passes validation, False otherwise.
            - errors: List of error dictionaries, each containing:
                - "path": JSON path to the erroneous field (e.g., "$.address.city")
                - "message": Human-readable error description
                - "error_type": Type of validation error (e.g., "required", "type", "pattern")
        """
        errors: List[Dict[str, Any]] = []
        try:
            validate(instance=data, schema=self._schema)
            return True, errors
        except ValidationError as e:
            return False, self._collect_errors(e)

    def _collect_errors(self, error: ValidationError) -> List[Dict[str, Any]]:
        """
        Recursively collect all validation errors into a structured list.

        Args:
            error: The root ValidationError from jsonschema.

        Returns:
            A list of error dictionaries.
        """
        errors: List[Dict[str, Any]] = []

        def _extract(error: ValidationError) -> None:
            # If the error has children (e.g., from anyOf, oneOf) we traverse them.
            if error.context:
                for child in error.context:
                    _extract(child)
                return

            # Build a human-readable path using the absolute_uri attribute
            # (jsonschema uses JSON pointers; we convert to dot notation for clarity)
            path = self._format_path(error.absolute_path)
            error_type = error.validator if error.validator else "unknown"
            # For better clarity, map common validator names to user-friendly types
            error_type_mapping = {
                "required": "required_field",
                "type": "type_mismatch",
                "pattern": "pattern_mismatch",
                "enum": "invalid_enum_value",
                "minimum": "value_too_small",
                "maximum": "value_too_large",
                "minLength": "string_too_short",
                "maxLength": "string_too_long",
                "additionalProperties": "unexpected_property",
                "oneOf": "no_matching_schema",
                "anyOf": "no_matching_schema",
                "allOf": "schema_mismatch",
                "const": "value_mismatch",
            }
            user_friendly_type = error_type_mapping.get(error_type, error_type)

            errors.append(
                {
                    "path": f"$.{path}" if path else "$",
                    "message": error.message,
                    "error_type": user_friendly_type,
                }
            )

        _extract(error)
        return errors

    @staticmethod
    def _format_path(path: Any) -> str:
        """
        Convert a jsonschema path (list of segments) to a dot-separated JSON path.

        Args:
            path: A deque or list of path segments from absolute_path.

        Returns:
            A string representation like "address.city" or "items[0].name".
        """
        segments = []
        for segment in path:
            if isinstance(segment, int):
                segments.append(f"[{segment}]")
            else:
                # Append dot only if the previous segment is not an array index
                # (because array indices start with '[' and don't need a dot before)
                if segments and not segments[-1].endswith("]"):
                    segments.append(".")
                segments.append(str(segment))
        return "".join(segments)

    @property
    def schema(self) -> Dict[str, Any]:
        """Return the schema used by this service (read-only)."""
        return self._schema


# Example usage (if run as a script, not required for the module)
if __name__ == "__main__":
    # Define a sample JSON Schema
    sample_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["name", "age", "email"],
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "minimum": 0, "maximum": 150},
            "email": {"type": "string", "pattern": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"},
            "address": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "zip": {"type": "string", "pattern": "^[0-9]{5}$"}
                },
                "required": ["city"]
            }
        }
    }

    # Create service
    service = DataValidationService(sample_schema)

    # Test data: valid
    valid_data = {
        "name": "Alice",
        "age": 30,
        "email": "alice@example.com",
        "address": {"city": "Wonderland", "zip": "12345"}
    }
    is_valid, errors = service.validate(valid_data)
    print("Valid data:", is_valid, errors)

    # Test data: invalid
    invalid_data = {
        "name": 42,                  # type error
        "email": "not-an-email",     # pattern error
        "address": {"zip": "12"}     # missing required field 'city', and zip pattern mismatch (too short)
    }
    is_valid, errors = service.validate(invalid_data)
    print("Invalid data:", is_valid)
    for err in errors:
        print(f"  Path: {err['path']}, Type: {err['error_type']}, Message: {err['message']}")