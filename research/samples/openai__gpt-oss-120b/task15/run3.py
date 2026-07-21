"""
json_validator.py

A lightweight JSON data‑validation service.

Features
--------
* Load a JSON schema from a file or a string.
* Validate Python data structures (typically the result of ``json.loads``)
  against the schema.
* Perform required‑field checks, type checking, and regular‑expression
  pattern matching for strings.
* Return a list of human‑readable error messages; an empty list means the
  data is valid.

The implementation relies on the widely‑used ``jsonschema`` package (Apache‑2.0)
and the Python standard library only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence, Union

import jsonschema
from jsonschema import Draft7Validator, ValidationError as JsonSchemaError

__all__: Sequence[str] = ("JSONValidationError", "load_schema", "JSONValidator")


class JSONValidationError(Exception):
    """
    Raised when the supplied schema cannot be parsed or is invalid.

    Attributes
    ----------
    message: str
        Human‑readable description of the problem.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message: str = message


def _read_file(path: Union[str, Path]) -> str:
    """
    Safely read the contents of a file.

    Parameters
    ----------
    path: Union[str, Path]
        Path to the file to read.

    Returns
    -------
    str
        The file contents.

    Raises
    ------
    JSONValidationError
        If the file cannot be opened or read.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError as exc:
        raise JSONValidationError(f"Unable to read schema file '{path}': {exc}") from exc


def load_schema(source: Union[str, Path, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Load a JSON schema from a string, a file path, or a pre‑parsed dictionary.

    Parameters
    ----------
    source : Union[str, Path, Dict[str, Any]]
        The schema source. If a string is supplied, the function attempts to
        interpret it as JSON; if the string corresponds to a readable file path,
        the file is read. If a ``dict`` is supplied it is returned unchanged.

    Returns
    -------
    Dict[str, Any]
        The parsed JSON schema.

    Raises
    ------
    JSONValidationError
        If the schema cannot be parsed or does not conform to the JSON Schema
        Draft‑7 meta‑schema.
    """
    # Direct dictionary – assumed already validated.
    if isinstance(source, dict):
        schema = source
    else:
        # Resolve a possible file path.
        if isinstance(source, (str, Path)) and Path(source).is_file():
            raw = _read_file(source)
        else:
            raw = str(source)

        try:
            schema = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise JSONValidationError(f"Invalid JSON schema: {exc}") from exc

    # Validate that the schema itself is a valid Draft‑7 schema.
    try:
        jsonschema.Draft7Validator.check_schema(schema)
    except JsonSchemaError as exc:
        raise JSONValidationError(f"Schema validation error: {exc.message}") from exc

    return schema


class JSONValidator:
    """
    Validate Python objects against a JSON Schema (Draft‑7).

    Parameters
    ----------
    schema : Dict[str, Any]
        The JSON Schema definition.

    Notes
    -----
    The validator is thread‑safe because ``jsonschema.Draft7Validator`` is
    immutable after construction.
    """

    def __init__(self, schema: Dict[str, Any]) -> None:
        self._schema: Dict[str, Any] = schema
        self._validator: Draft7Validator = Draft7Validator(schema)

    @property
    def schema(self) -> Dict[str, Any]:
        """Return the original schema dictionary."""
        return self._schema

    def validate(self, data: Any) -> List[str]:
        """
        Validate ``data`` against the stored schema.

        Parameters
        ----------
        data : Any
            The Python object to validate (e.g., the result of ``json.loads``).

        Returns
        -------
        List[str]
            A list of error messages. The list is empty when ``data`` conforms
            to the schema.

        Example
        -------
        >>> validator = JSONValidator({"type": "object", "properties": {"name": {"type": "string"}}})
        >>> validator.validate({"name": 123})
        ["'name': 123 is not of type 'string'"]
        """
        errors: List[str] = []
        for err in self._validator.iter_errors(data):
            # Build a readable path like "address.street"
            path = ".".join([str(p) for p in err.absolute_path]) if err.absolute_path else "<root>"
            # Use the message from jsonschema, but prepend the path.
            errors.append(f"{path}: {err.message}")
        return errors

    def is_valid(self, data: Any) -> bool:
        """
        Shortcut that returns ``True`` if ``data`` conforms to the schema,
        ``False`` otherwise.

        Parameters
        ----------
        data : Any
            The data to test.

        Returns
        -------
        bool
            Validation result.
        """
        return not self.validate(data)


# --------------------------------------------------------------------------- #
# Helper utilities (optional but useful for end‑users)
# --------------------------------------------------------------------------- #

def _compile_pattern(pattern: str) -> re.Pattern:
    """
    Compile a regular expression pattern safely.

    Parameters
    ----------
    pattern : str
        The regex pattern.

    Returns
    -------
    re.Pattern
        Compiled regular expression.

    Raises
    ------
    JSONValidationError
        If the pattern is invalid.
    """
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise JSONValidationError(f"Invalid regular expression pattern '{pattern}': {exc}") from exc


def validate_json_string(
    json_string: str,
    schema_source: Union[str, Path, Dict[str, Any]],
) -> List[str]:
    """
    Convenience function that parses a JSON string and validates it against a
    schema supplied as a file path, raw JSON string, or dictionary.

    Parameters
    ----------
    json_string : str
        JSON document to validate.
    schema_source : Union[str, Path, Dict[str, Any]]
        Schema definition (see :func:`load_schema`).

    Returns
    -------
    List[str]
        Validation error messages; empty if valid.

    Raises
    ------
    JSONValidationError
        If the JSON document cannot be parsed.
    """
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as exc:
        raise JSONValidationError(f"Invalid JSON document: {exc}") from exc

    schema = load_schema(schema_source)
    validator = JSONValidator(schema)
    return validator.validate(data)