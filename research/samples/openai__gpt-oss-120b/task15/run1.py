"""
json_validator.py

A tiny JSON data‑validation service built around the ``jsonschema`` package.
It loads a JSON schema, validates Python data structures against it, and
returns a detailed list of validation errors.

Features
--------
* Required‑field, type‑checking and pattern‑matching support via JSON Schema.
* Typed public API with comprehensive docstrings.
* Explicit error handling – schema loading and validation errors are wrapped
  in dedicated exception classes.
* No use of ``eval`` or other unsafe constructs – the module follows security
  best practices.

Only the Python standard library and the widely‑used ``jsonschema`` package are
required.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from jsonschema import Draft7Validator, ValidationError  # type: ignore[import]

__all__: Sequence[str] = (
    "SchemaLoadError",
    "DataValidationError",
    "ValidationErrorInfo",
    "load_schema",
    "load_json",
    "validate",
)


class SchemaLoadError(RuntimeError):
    """Raised when a JSON schema cannot be loaded or parsed."""


class DataValidationError(RuntimeError):
    """Raised when validation fails for a JSON document.

    The ``errors`` attribute contains a list of :class:`ValidationErrorInfo`
    instances describing each problem.
    """

    def __init__(self, errors: List["ValidationErrorInfo"]) -> None:
        self.errors = errors
        super().__init__(f"{len(errors)} validation error(s) encountered.")


@dataclass(frozen=True)
class ValidationErrorInfo:
    """A lightweight, serialisable representation of a ``jsonschema`` error."""

    message: str
    """Human‑readable description of the validation problem."""

    path: List[str | int]
    """JSON pointer path (as a list) to the offending element."""

    validator: str
    """Name of the JSON‑Schema validator that failed (e.g. ``type``, ``pattern``)."""

    validator_value: Any
    """The value from the schema that caused the failure (e.g. expected type)."""

    instance: Any
    """The actual value from the data that failed validation."""


def _json_path(error: ValidationError) -> List[str | int]:
    """
    Convert a ``jsonschema.ValidationError``'s absolute path to a list.

    The path elements are either property names (``str``) or array indices
    (``int``), matching the JSON Pointer specification.
    """
    return list(error.absolute_path)


def _error_to_info(error: ValidationError) -> ValidationErrorInfo:
    """
    Transform a ``jsonschema.ValidationError`` into a :class:`ValidationErrorInfo`.
    """
    return ValidationErrorInfo(
        message=error.message,
        path=_json_path(error),
        validator=error.validator,
        validator_value=error.validator_value,
        instance=error.instance,
    )


def load_schema(schema_path: str | pathlib.Path) -> Dict[str, Any]:
    """
    Load a JSON schema from a file.

    Parameters
    ----------
    schema_path:
        Path to a file containing a JSON schema.

    Returns
    -------
    dict
        The parsed JSON schema.

    Raises
    ------
    SchemaLoadError
        If the file cannot be read or does not contain valid JSON.
    """
    try:
        path = pathlib.Path(schema_path).expanduser().resolve(strict=True)
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaLoadError(f"Failed to load schema from {schema_path!s}: {exc}") from exc


def load_json(data_path: str | pathlib.Path) -> Any:
    """
    Load JSON data from a file.

    Parameters
    ----------
    data_path:
        Path to a JSON document.

    Returns
    -------
    Any
        The parsed JSON data (usually ``dict`` or ``list``).

    Raises
    ------
    OSError
        If the file cannot be opened.
    json.JSONDecodeError
        If the file does not contain valid JSON.
    """
    path = pathlib.Path(data_path).expanduser().resolve(strict=True)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate(data: Any, schema: Dict[str, Any]) -> List[ValidationErrorInfo]:
    """
    Validate ``data`` against ``schema`` using Draft‑7 of the JSON Schema spec.

    Parameters
    ----------
    data:
        The Python object to validate (e.g., result of ``json.load``).
    schema:
        A JSON Schema represented as a ``dict``.

    Returns
    -------
    list[ValidationErrorInfo]
        A list of validation errors; empty if validation succeeded.

    Raises
    ------
    DataValidationError
        If one or more validation errors are found. The ``errors`` attribute
        of the exception contains the full list.
    """
    try:
        validator = Draft7Validator(schema)
    except Exception as exc:  # pragma: no cover – defensive programming
        raise SchemaLoadError(f"The provided schema is invalid: {exc}") from exc

    errors = [_error_to_info(err) for err in sorted(validator.iter_errors(data), key=lambda e: e.path)]

    if errors:
        raise DataValidationError(errors)

    return []  # Explicit empty list for successful validation