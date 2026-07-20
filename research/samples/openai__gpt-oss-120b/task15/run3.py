"""
json_validation_service.py

A lightweight JSON validation service using jsonschema.

Features:
- Schema definition in JSON (Python dict or JSON file)
- Required fields, type checking, pattern matching for strings
- Detailed error reporting with path information
- Type hints, docstrings, and safe handling of external references

Only standard library and `jsonschema` are required.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence, Union

import jsonschema
from jsonschema import Draft7Validator, RefResolver, ValidationError as JsonSchemaError

# ---------------------------------------------------------------------------


@dataclass
class ValidationErrorDetail:
    """Detailed information about a single validation error."""

    message: str
    path: str
    schema_path: str
    validator: str
    validator_value: Any

    def to_dict(self) -> Dict[str, Any]:
        """Return a serializable representation."""
        return {
            "message": self.message,
            "path": self.path,
            "schema_path": self.schema_path,
            "validator": self.validator,
            "validator_value": self.validator_value,
        }


class JSONValidationError(Exception):
    """Raised when JSON data does not conform to the provided schema."""

    def __init__(self, errors: Sequence[ValidationErrorDetail]) -> None:
        self.errors = list(errors)
        super_message = f"{len(self.errors)} validation error(s) occurred."
        super().__init__(super_message)

    def __str__(self) -> str:
        return "\n".join(
            f"{i+1}. {e.path or '<root>'}: {e.message}" for i, e in enumerate(self.errors)
        )

    def to_json(self) -> str:
        """Return a JSON string with all error details."""
        return json.dumps([e.to_dict() for e in self.errors], indent=2)


# ---------------------------------------------------------------------------


class JSONValidator:
    """
    Service for validating JSON data against a JSON Schema.

    Parameters
    ----------
    schema : Mapping[str, Any] | str | pathlib.Path
        A JSON Schema as a Python mapping or a path to a JSON file containing the schema.
    resolver : RefResolver | None
        Optional custom resolver for handling $ref. By default, a safest resolver is used.
    """

    def __init__(
        self,
        schema: Union[Mapping[str, Any], str, pathlib.Path],
        *,
        resolver: RefResolver | None = None,
    ) -> None:
        self._schema = self._load_schema(schema)
        self._resolver = resolver or self._default_resolver(self._schema)
        self._validator = Draft7Validator(self._schema, resolver=self._resolver)

    @staticmethod
    def _load_schema(source: Union[Mapping[str, Any], str, pathlib.Path]) -> Dict[str, Any]:
        """Load a JSON schema from a dict, a JSON string, or a file path."""
        if isinstance(source, Mapping):
            return dict(source)
        if isinstance(source, (str, pathlib.Path)):
            path = pathlib.Path(source).expanduser().resolve()
            if not path.is_file():
                raise FileNotFoundError(f"Schema file not found: {path}")
            try:
                with path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in schema file {path}: {exc}") from exc
        raise TypeError("Schema must be a dict, a file path, or a JSON string.")

    @staticmethod
    def _default_resolver(schema: Mapping[str, Any]) -> RefResolver:
        """
        Create a safe resolver that disables fetching remote schemas.
        Only local references within the provided schema are allowed.
        """
        # Empty store prevents external $ref lookups.
        store = {}
        # Use the base URI of the schema if provided.
        base_uri = schema.get("$id", "http://example.com/")
        return RefResolver(base_uri=base_uri, referrer=schema, store=store)

    @staticmethod
    def _format_path(error: JsonSchemaError) -> str:
        """Convert a jsonschema error path to a dot‑separated string."""
        parts = list(error.absolute_path)
        return ".".join(str(p) for p in parts) if parts else ""

    @staticmethod
    def _format_schema_path(error: JsonSchemaError) -> str:
        """Convert a jsonschema error schema_path to a dot‑separated string."""
        parts = list(error.absolute_schema_path)
        return ".".join(str(p) for p in parts) if parts else ""

    def _collect_errors(self, data: Any) -> List[ValidationErrorDetail]:
        """Collect all validation errors from the validator."""
        errors: List[ValidationErrorDetail] = []
        for err in sorted(self._validator.iter_errors(data), key=lambda e: e.path):
            detail = ValidationErrorDetail(
                message=err.message,
                path=self._format_path(err),
                schema_path=self._format_schema_path(err),
                validator=err.validator,
                validator_value=err.validator_value,
            )
            errors.append(detail)
        return errors

    def validate(self, data: Union[Mapping[str, Any], str]) -> Mapping[str, Any]:
        """
        Validate JSON data against the schema.

        Parameters
        ----------
        data : Mapping[str, Any] | str
            JSON data as a Python mapping or a JSON string.

        Returns
        -------
        Mapping[str, Any]
            The original data if validation succeeds.

        Raises
        ------
        JSONValidationError
            If validation fails. Contains a list of detailed errors.
        ValueError
            If the provided data string is not valid JSON.
        TypeError
            If the data is not a mapping or a JSON string.
        """
        parsed_data = self._parse_data(data)
        errors = self._collect_errors(parsed_data)
        if errors:
            raise JSONValidationError(errors)
        # If no errors, return a (potentially) immutable view of the data.
        return parsed_data

    @staticmethod
    def _parse_data(source: Union[Mapping[str, Any], str]) -> Mapping[str, Any]:
        """Parse JSON data from a dict or string."""
        if isinstance(source, Mapping):
            return dict(source)
        if isinstance(source, str):
            try:
                result = json.loads(source)
                if not isinstance(result, Mapping):
                    raise ValueError("JSON data must be an object at the top level.")
                return result
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON data: {exc}") from exc
        raise TypeError("Data must be a dict or a JSON string.")


# ---------------------------------------------------------------------------


def example_usage() -> None:
    """
    Demonstrate usage of JSONValidator.

    This function is not executed on import. It shows how to:
    - Define a schema
    - Validate correct and incorrect data
    - Handle validation errors
    """
    schema = {
        "$id": "http://example.com/person.schema.json",
        "type": "object",
        "required": ["name", "email", "age"],
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "email": {"type": "string", "format": "email", "pattern": r"^[^@]+@[^@]+\.[^@]+$"},
            "age": {"type": "integer", "minimum": 0},
            "address": {
                "type": "object",
                "required": ["city", "postalCode"],
                "properties": {
                    "city": {"type": "string"},
                    "postalCode": {"type": "string", "pattern": r"^\d{5}$"},
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }

    validator = JSONValidator(schema)

    valid_json = {
        "name": "Alice",
        "email": "alice@example.com",
        "age": 30,
        "address": {"city": "Wonderland", "postalCode": "12345"},
    }

    invalid_json = {
        "name": "",
        "email": "bad-email",
        "age": -5,
        "address": {"city": "Nowhere",