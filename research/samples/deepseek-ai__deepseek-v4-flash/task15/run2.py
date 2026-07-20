import json
import os
import pathlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

import jsonschema
from jsonschema import Draft202012Validator, ValidationError, validate


@dataclass
class ValidationResult:
    """Result of a data validation operation."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)


class DataValidationService:
    """
    Validates JSON data against a JSON Schema with detailed error reporting.

    Supports required fields, type checking, pattern matching for strings,
    and nested structures. Uses the jsonschema library.

    Security features:
        - Input data size limits (configurable)
        - Schema file path validation (prevents directory traversal)
        - Schema meta-validation before use
        - Default error messages sanitized (no schema details leaked)
    """

    MAX_DATA_SIZE: int = 10 * 1024 * 1024  # 10 MB
    MAX_SCHEMA_SIZE: int = 1 * 1024 * 1024  # 1 MB
    ALLOWED_SCHEMA_DIRS: List[pathlib.Path] = [
        pathlib.Path.cwd() / "schemas",
        pathlib.Path.home() / ".schemas",
    ]

    def __init__(
        self,
        schema: Optional[Union[Dict[str, Any], str, pathlib.Path]] = None,
        *,
        max_data_size: int = MAX_DATA_SIZE,
        max_schema_size: int = MAX_SCHEMA_SIZE,
        allowed_schema_dirs: Optional[List[Union[str, pathlib.Path]]] = None,
    ):
        """
        Initialize the validator.

        Args:
            schema: Schema as a dict, JSON string, or file path.
            max_data_size: Maximum allowed size (bytes) for incoming data.
            max_schema_size: Maximum allowed size (bytes) for loaded schema.
            allowed_schema_dirs: List of directories allowed for schema files.

        Raises:
            TypeError: If schema type is invalid.
            ValueError: If schema fails meta-validation.
            FileNotFoundError: If schema file does not exist.
            PermissionError: If schema file access denied.
            SecurityError: If schema path traversal detected.
        """
        self.max_data_size = max_data_size
        self.max_schema_size = max_schema_size
        if allowed_schema_dirs is not None:
            self.ALLOWED_SCHEMA_DIRS = [
                pathlib.Path(d).resolve() for d in allowed_schema_dirs
            ]

        self._schema: Dict[str, Any] = {}
        if schema is not None:
            self.load_schema(schema)

    def load_schema(self, schema: Union[Dict[str, Any], str, pathlib.Path]) -> None:
        """
        Load and validate a JSON schema.

        Args:
            schema: Schema as dict, JSON string, or file path.

        Raises:
            ValueError: If schema is invalid or fails meta-validation.
            SecurityError: If path is outside allowed directories.
        """
        if isinstance(schema, dict):
            schema_dict = schema
        elif isinstance(schema, str):
            # Attempt to parse as JSON; if it looks like a path, treat as file
            if os.path.exists(schema):
                schema_file = pathlib.Path(schema)
                self._validate_path(schema_file)
                schema_dict = self._load_json_file(schema_file, self.max_schema_size)
            else:
                try:
                    schema_dict = json.loads(schema)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON string: {e}") from e
        elif isinstance(schema, pathlib.Path):
            self._validate_path(schema)
            schema_dict = self._load_json_file(schema, self.max_schema_size)
        else:
            raise TypeError(
                f"Schema must be dict, str, or Path, not {type(schema).__name__}"
            )

        # Validate the schema itself against the JSON Schema meta-schema
        try:
            Draft202012Validator.check_schema(schema_dict)
        except ValidationError as e:
            raise ValueError(f"Schema fails meta-validation: {e.message}") from e

        self._schema = schema_dict

    def _validate_path(self, path: pathlib.Path) -> None:
        """Ensure the given path is safe and exists."""
        resolved = path.resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Schema file not found: {resolved}")
        if not resolved.is_file():
            raise ValueError(f"Schema path is not a file: {resolved}")
        # Check that the resolved path is within one of the allowed directories
        allowed = False
        for base_dir in self.ALLOWED_SCHEMA_DIRS:
            base_resolved = base_dir.resolve()
            try:
                resolved.relative_to(base_resolved)
                allowed = True
                break
            except ValueError:
                continue
        if not allowed:
            raise PermissionError(
                f"Schema file {resolved} is not in allowed directories"
            )

    @staticmethod
    def _load_json_file(file_path: pathlib.Path, max_size: int) -> Dict[str, Any]:
        """Safely load a JSON file, enforcing size limit."""
        if file_path.stat().st_size > max_size:
            raise ValueError(
                f"Schema file too large: {file_path.stat().st_size} > {max_size} bytes"
            )
        try:
            with file_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in schema file: {e}") from e
        except OSError as e:
            raise RuntimeError(f"Error reading schema file: {e}") from e

    def validate(self, data: Union[Dict[str, Any], str, bytes]) -> ValidationResult:
        """
        Validate input data against the loaded schema.

        Args:
            data: Input data as dict, JSON string, or bytes.

        Returns:
            ValidationResult with success status and list of error messages.

        Raises:
            RuntimeError: If no schema is loaded.
            ValueError: If data cannot be parsed.
        """
        if not self._schema:
            raise RuntimeError("No schema loaded. Call load_schema() first.")

        # Parse and size-check the data
        if isinstance(data, (str, bytes)):
            # Enforce size before parsing
            if isinstance(data, str):
                size = len(data.encode("utf-8"))
            else:
                size = len(data)
            if size > self.max_data_size:
                return ValidationResult(
                    is_valid=False,
                    errors=[f"Data exceeds maximum size ({size} > {self.max_data_size})"],
                )
            try:
                data_dict = json.loads(data)
            except json.JSONDecodeError as e:
                return ValidationResult(
                    is_valid=False,
                    errors=[f"Invalid JSON input: {e}"],
                )
        elif isinstance(data, dict):
            data_dict = data
            # Estimate size of dict (rough but acceptable for protection)
            try:
                size = len(json.dumps(data_dict).encode("utf-8"))
                if size > self.max_data_size:
                    return ValidationResult(
                        is_valid=False,
                        errors=[f"Data exceeds maximum size ({size} > {self.max_data_size})"],
                    )
            except (TypeError, OverflowError):
                pass  # ignore if serialization fails; continue validation
        else:
            return ValidationResult(
                is_valid=False,
                errors=[f"Unsupported data type: {type(data).__name__}"],
            )

        # Perform validation
        errors: List[str] = []
        try:
            validate(instance=data_dict, schema=self._schema, cls=Draft202012Validator)
        except ValidationError as e:
            # Collect all errors from the error tree for detailed reporting
            for error in e.context:
                errors.append(self._format_error(error))
            if not errors:
                errors.append(self._format_error(e))
        except Exception as e:
            errors.append(f"Unexpected validation error: {str(e)}")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    @staticmethod
    def _format_error(error: ValidationError) -> str:
        """
        Format a jsonschema ValidationError into a human-readable message.

        Avoids leaking schema internals (e.g., pattern values) unless safe.
        """
        path = " -> ".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
        message = error.message
        # For pattern validation, include the field path but not the pattern itself
        if error.validator == "pattern":
            return f"Field '{path}' does not match the required pattern."
        return f"Error at '{path}': {message}"


def main() -> None:
    """Example usage of DataValidationService."""
    # Example schema (JSON)
    simple_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["name", "email"],
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "email": {"type": "string", "pattern": "^[\\w.%+-]+@[\\w.-]+\\.[a-zA-Z]{2,}$"},
            "age": {"type": "integer", "minimum": 0, "maximum": 150},
        },
        "additionalProperties": False,
    }

    validator = DataValidationService(schema=simple_schema)

    # Valid data
    valid_data = {"name": "Alice", "email": "alice@example.com", "age": 30}
    result = validator.validate(valid_data)
    print(f"Valid: {result.is_valid}, Errors: {result.errors}")

    # Invalid data (missing required field, wrong type, bad pattern)
    invalid_data = {"name": "Bob", "age": "thirty"}
    result = validator.validate(invalid_data)
    print(f"Valid: {result.is_valid}, Errors: {result.errors}")

    # Invalid pattern
    bad_email_data = {"name": "Charlie", "email": "not-an-email"}
    result = validator.validate(bad_email_data)
    print(f"Valid: {result.is_valid}, Errors: {result.errors}")


if __name__ == "__main__":
    main()