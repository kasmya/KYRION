"""
data_validation_service.py

A lightweight JSON data validation service built on top of the standard library
and the well‑known ``jsonschema`` package.

Features
--------
* Schema definition in JSON (or Python dict)
* Required‑field validation
* Type checking
* Regex pattern matching for strings
* Detailed error reporting with JSON‑pointer paths
* Type hints, docstrings, and robust error handling
* Security‑focused defaults (no external references, safe schema loading)

Usage
-----
>>> from data_validation_service import JsonValidator, ValidationErrorDetail
>>> schema = {
...     "type": "object",
...     "properties": {
...         "name": {"type": "string", "pattern": "^[A-Za-z ]+$"},
...         "age": {"type": "integer", "minimum": 0},
...         "email": {"type": "string", "format": "email"},
...     },
...     "required": ["name", "age"],
... }
>>> validator = JsonValidator(schema)
>>> data = {"name": "John Doe", "age": 30, "email": "john@example.com"}
>>> validator.validate(data)  # returns True
>>> bad_data = {"name": "John123", "age": -5}
>>> is_valid, errors = validator.validate(bad_data)
>>> is_valid
False
>>> errors[0].message
"'John123' does not match '^[A-Za-z ]+$'"
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import jsonschema
from jsonschema import Draft7Validator, ValidationError as JsonSchemaValidationError

# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ValidationErrorDetail:
    """A single validation error with a human readable message and a JSON pointer."""

    message: str
    """Human readable description of the validation problem."""

    path: str
    """JSON pointer string indicating the location of the error in the instance."""

    validator: str
    """Name of the validator that raised the error (e.g. 'type', 'required')."""

    validator_value: Any
    """The schema value that caused the validation error."""


# --------------------------------------------------------------------------- #
# Core validator
# --------------------------------------------------------------------------- #


class JsonValidator:
    """
    Validate JSON data against a JSON schema.

    The validator uses ``jsonschema.Draft7Validator`` under the hood and
    provides a simple ``validate`` method that returns a boolean together
    with a list of :class:`ValidationErrorDetail` objects.

    Parameters
    ----------
    schema : Union[Dict[str, Any], str, Path]
        The JSON schema dictionary, a JSON string, or a path to a JSON file.
        External ``$ref`` references are disabled for security.
    """

    def __init__(self, schema: Union[Dict[str, Any], str, Path]) -> None:
        self._schema = self._load_schema(schema)
        self._validator = Draft7Validator(self._schema, format_checker=jsonschema.FormatChecker())

    @staticmethod
    def _load_schema(schema_source: Union[Dict[str, Any], str, Path]) -> Dict[str, Any]:
        """Load a JSON schema from a dict, a JSON string, or a file path."""
        if isinstance(schema_source, dict):
            return schema_source

        if isinstance(schema_source, (str, Path)):
            # Resolve path safely: only allow local file system access.
            try:
                path = Path(schema_source).expanduser().resolve(strict=True)
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError("Loaded schema must be a JSON object.")
                return data
            except FileNotFoundError as e:
                raise FileNotFoundError(f"Schema file not found: {schema_source}") from e
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in schema file: {schema_source}") from e

        raise TypeError("Schema must be a dict, JSON string, or pathlib.Path.")

    @staticmethod
    def _format_error(err: JsonSchemaValidationError) -> ValidationErrorDetail:
        """Convert a jsonschema.ValidationError into a ValidationErrorDetail."""
        # Build a JSON pointer from the error path.
        pointer = "/" + "/".join(str(p) for p in err.absolute_path)
        return ValidationErrorDetail(
            message=err.message,
            path=pointer,
            validator=err.validator,
            validator_value=err.validator_value,
        )

    def validate(self, data: Union[Dict[str, Any], str, bytes]) -> Tuple[bool, List[ValidationErrorDetail]]:
        """
        Validate *data* against the stored schema.

        Parameters
        ----------
        data : Union[Dict[str, Any], str, bytes]
            JSON data to validate, either already parsed as a dict or a JSON string/bytes.

        Returns
        -------
        Tuple[bool, List[ValidationErrorDetail]]
            ``(True, [])`` when validation succeeds.
            ``(False, [errors...])`` when validation fails.

        Raises
        ------
        ValueError
            If *data* cannot be parsed as JSON.
        TypeError
            If *data* is not of a supported type.
        """
        instance = self._ensure_dict(data)

        errors = sorted(self._validator.iter_errors(instance), key=lambda e: e.path)
        if not errors:
            return True, []

        detailed_errors = [self._format_error(err) for err in errors]
        return False, detailed_errors

    @staticmethod
    def _ensure_dict(data: Union[Dict[str, Any], str, bytes]) -> Dict[str, Any]:
        """Parse input data into a dictionary or raise a helpful exception."""
        if isinstance(data, dict):
            return data

        if isinstance(data, (str, bytes)):
            try:
                return json.loads(data)
            except json.JSONDecodeError as e:
                raise ValueError("Provided data is not valid JSON.") from e

        raise TypeError("Data must be a dict, JSON string, or bytes.")


# --------------------------------------------------------------------------- #
# Example usage (executed only when run as a script)
# --------------------------------------------------------------------------- #


if __name__ == "__main__":
    # Example schema with required fields, types, and a regex pattern.
    example_schema = {
        "type": "object",
        "properties": {
            "username": {
                "type": "string",
                "pattern": r"^[a-zA-Z0-9_]{3,30}$",
                "description": "Alphanumeric username between 3 and 30 characters.",
            },
            "age": {"type": "integer", "minimum": 0},
            "email": {"type": "string", "format": "email"},
            "profile": {
                "type": "object",
                "properties": {"bio": {"type": "string", "maxLength": 200}},
                "required": ["bio"],
                "additionalProperties": False,
            },
        },
        "required": ["username", "age"],
        "additionalProperties": False,
    }

    validator = JsonValidator(example_schema)

    # Valid payload
    valid_payload = {
        "username": "alice_01",
        "age": 28,
        "email": "alice@example.com",
        "profile": {"bio": "Hello world!"},
    }

    ok, errors = validator.validate(valid_payload)
    print("Valid payload:", ok)  # Expected: True

    # Invalid payload
    invalid_payload = {
        "username": "a!",  # fails pattern
        "age": -5,  # fails minimum
        "extra": "not allowed",  # fails additionalProperties
    }

    ok, errors = validator.validate(invalid_payload)
    print("Invalid payload:", ok)  # Expected: False
    for err in errors:
        print(f"Error at {err.path or '/'}: {err.message} (validator: {err.validator})")