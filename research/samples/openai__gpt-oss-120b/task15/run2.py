"""
json_validator.py

A lightweight JSON data‑validation service.

Features
--------
- Load a JSON schema from a file or a Python dictionary.
- Validate JSON data against the schema.
- Perform required‑field checks, type checking, and pattern matching.
- Return a list of human‑readable error messages.
- Explicit error handling and clear type hints.

The implementation relies only on the Python standard library and the
widely‑used ``jsonschema`` package (https://pypi.org/project/jsonschema/).
"""

from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence, Union

import jsonschema
from jsonschema import Draft7Validator, ValidationError as JsonSchemaError

# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ValidationError:
    """Container for a single validation error.

    Attributes
    ----------
    field_path: str
        JSON pointer (e.g. ``/address/street``) indicating where the error
        occurred.
    message: str
        Human‑readable description of the problem.
    """

    field_path: str
    message: str


# --------------------------------------------------------------------------- #
# Helper functions
# --------------------------------------------------------------------------- #


def _load_json_file(file_path: Union[str, pathlib.Path]) -> Mapping[str, Any]:
    """Read a JSON file and return its content.

    Parameters
    ----------
    file_path:
        Path to the JSON file.

    Returns
    -------
    Mapping[str, Any]
        Parsed JSON object.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    json.JSONDecodeError
        If the file does not contain valid JSON.
    """
    path = pathlib.Path(file_path).expanduser().resolve(strict=True)
    # Security: open the file in read‑only text mode with explicit encoding.
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _json_pointer_to_path(pointer: str) -> str:
    """Convert a JSON pointer (as used by ``jsonschema``) to a dotted path.

    Example
    -------
    >>> _json_pointer_to_path("/address/street")
    'address.street'
    """
    parts = pointer.lstrip("/").split("/")
    # Unescape according to RFC 6901
    parts = [p.replace("~1", "/").replace("~0", "~") for p in parts]
    return ".".join(parts)


def _collect_errors(validator: Draft7Validator, data: Mapping[str, Any]) -> List[ValidationError]:
    """Run the validator and collect errors in a friendly format.

    Parameters
    ----------
    validator:
        An instance of :class:`jsonschema.Draft7Validator`.
    data:
        The JSON document to validate.

    Returns
    -------
    List[ValidationError]
        All validation errors found; empty list if the document is valid.
    """
    errors: List[ValidationError] = []
    for err in sorted(validator.iter_errors(data), key=lambda e: e.path):
        field_path = _json_pointer_to_path(err.absolute_path or "")
        # Provide a concise message; include the failing value for context.
        message = f"{err.message}"
        if err.instance is not None:
            # Avoid leaking huge structures.
            instance_repr = json.dumps(err.instance, ensure_ascii=False)[:80]
            message += f" (got: {instance_repr})"
        errors.append(ValidationError(field_path=field_path, message=message))
    return errors


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def load_schema(source: Union[str, pathlib.Path, Mapping[str, Any]]) -> Mapping[str, Any]:
    """Load a JSON schema from a file path or a ready‑made dictionary.

    Parameters
    ----------
    source:
        Either a path to a JSON schema file or a dictionary representing the
        schema directly.

    Returns
    -------
    Mapping[str, Any]
        The parsed JSON schema.

    Raises
    ------
    TypeError
        If *source* is of an unsupported type.
    FileNotFoundError, json.JSONDecodeError
        Propagated from the underlying file‑reading routine.
    """
    if isinstance(source, (str, pathlib.Path)):
        return _load_json_file(source)
    if isinstance(source, Mapping):
        # Defensive copy to avoid accidental mutation by callers.
        return dict(source)
    raise TypeError(
        f"Unsupported schema source type: {type(source)!r}. "
        "Expected a file path or a mapping."
    )


def validate_json(
    data: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> List[ValidationError]:
    """Validate *data* against *schema* and return any errors found.

    This function uses the Draft‑7 JSON Schema specification via the
    ``jsonschema`` library. It checks required properties, data types,
    string patterns, numeric ranges, array constraints, etc., as defined
    by the supplied schema.

    Parameters
    ----------
    data:
        The JSON document (as a Python mapping) to validate.
    schema:
        The JSON Schema definition.

    Returns
    -------
    List[ValidationError]
        A list of validation problems; empty when the document conforms.

    Raises
    ------
    jsonschema.SchemaError
        If the provided schema itself is invalid.
    TypeError
        If *data* or *schema* is not a mapping.
    """
    if not isinstance(data, Mapping):
        raise TypeError(f"data must be a mapping, got {type(data)!r}")
    if not isinstance(schema, Mapping):
        raise TypeError(f"schema must be a mapping, got {type(schema)!r}")

    # jsonschema may raise SchemaError for malformed schemas – let it propagate.
    validator = Draft7Validator(schema)

    return _collect_errors(validator, data)


def validate_json_file(
    json_path: Union[str, pathlib.Path],
    schema_source: Union[str, pathlib.Path, Mapping[str, Any]],
) -> List[ValidationError]:
    """Convenience wrapper to validate a JSON file against a schema.

    Parameters
    ----------
    json_path:
        Path to the JSON document to validate.
    schema_source:
        Either a path to a JSON Schema file or a dictionary representing the
        schema.

    Returns
    -------
    List[ValidationError]
        Validation errors, if any.

    Raises
    ------
    FileNotFoundError, json.JSONDecodeError
        If the JSON document cannot be read or parsed.
    jsonschema.SchemaError
        If the schema is invalid.
    """
    data = _load_json_file(json_path)
    schema = load_schema(schema_source)
    return validate_json(data, schema)


# --------------------------------------------------------------------------- #
# Example usage (executed only when run as a script)
# --------------------------------------------------------------------------- #


def _example() -> None:
    """Run a tiny demonstration when the module is executed directly."""
    example_schema = {
        "type": "object",
        "required": ["name", "email"],
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "email": {
                "type": "string",
                "format": "email",
                "pattern": r"^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$",
            },
            "age": {"type": "integer", "minimum": 0},
        },
        "additionalProperties": False,
    }

    valid_data = {"name": "Alice", "email": "alice@example.com", "age": 30}
    invalid_data = {"name": "", "email": "not-an-email", "extra": "field"}

    print("Validating correct data:")
    for err in validate_json(valid_data, example_schema):
        print(f"- {err.field_path}: {err.message}")

    print("\nValidating incorrect data:")
    for err in validate_json(invalid_data, example_schema):
        print(f"- {err.field_path}: {err.message}")


if __name__ == "__main__":
    _example()