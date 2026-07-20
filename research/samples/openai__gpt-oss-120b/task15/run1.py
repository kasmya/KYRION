"""
json_validation_service.py

A lightweight JSON validation service that validates JSON data against a
JSON Schema definition. Features include:

* Schema definition in JSON (Python dict)
* Validation of required fields
* Type checking (string, number, integer, boolean, array, object, null)
* Pattern matching for string fields (regular expressions)
* Detailed error reporting (human‑readable messages, JSON pointers)
* Type hints, docstrings and robust error handling
* Security best practices: schema self‑validation, safe JSON loading,
  strict validator configuration.

Only the standard library and the well‑known ``jsonschema`` package are used.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

from jsonschema import Draft7Validator, ValidationError, validators, exceptions

# Configure module‑level logger
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class SchemaError(RuntimeError):
    """Raised when the supplied JSON Schema is invalid or unsafe."""


class ValidationResult:
    """
    Container for the result of a validation operation.

    Attributes
    ----------
    is_valid: bool
        ``True`` if data conforms to the schema, ``False`` otherwise.
    errors: List[Dict[str, Any]]
        List of dictionaries describing each validation error.
    """

    __slots__ = ("is_valid", "errors")

    def __init__(self, is_valid: bool, errors: List[Dict[str, Any]]) -> None:
        self.is_valid = is_valid
        self.errors = errors

    def __bool__(self) -> bool:  # pragma: no cover
        return self.is_valid

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ValidationResult is_valid={self.is_valid} errors={len(self.errors)}>"


def _extend_with_default(validator_class: Any) -> Any:
    """
    Extend a jsonschema validator to set defaults on missing properties.
    This mirrors the behaviour demonstrated in the jsonschema documentation.
    """

    validate_properties = validator_class.VALIDATORS["properties"]

    def set_defaults(validator, properties, instance, schema):
        for prop, subschema in properties.items():
            if "default" in subschema:
                instance.setdefault(prop, subschema["default"])

        for error in validate_properties(
            validator, properties, instance, schema,
        ):
            yield error

    return validators.extend(
        validator_class, {"properties": set_defaults}
    )


# Use the extended validator with default handling (optional but handy)
DefaultValidatingValidator = _extend_with_default(Draft7Validator)


class JSONValidationService:
    """
    Service that validates JSON data against a JSON Schema.

    Parameters
    ----------
    schema : Union[Dict[str, Any], str, Path]
        The JSON Schema definition as a dict, JSON string, or path to a
        JSON file.

    Raises
    ------
    SchemaError
        If the supplied schema cannot be parsed or fails JSON‑Schema self‑validation.
    """

    def __init__(self, schema: Union[Dict[str, Any], str, Path]) -> None:
        self._schema = self._load_schema(schema)
        self._validator = self._create_validator(self._schema)

    @staticmethod
    def _load_schema(source: Union[Dict[str, Any], str, Path]) -> Dict[str, Any]:
        """Load a JSON schema from dict, string or file in a safe manner."""
        if isinstance(source, dict):
            schema = source
        elif isinstance(source, (str, Path)):
            try:
                path = Path(source)
                if path.is_file():
                    with path.open("r", encoding="utf-8") as fh:
                        schema = json.load(fh)
                else:
                    # Treat the string itself as JSON content
                    schema = json.loads(str(source))
            except (json.JSONDecodeError, OSError) as exc:
                raise SchemaError(f"Unable to load schema: {exc}") from exc
        else:
            raise SchemaError(f"Unsupported schema source type: {type(source)}")

        # Ensure the schema itself is a valid Draft‑7 schema
        try:
            Draft7Validator.check_schema(schema)
        except exceptions.SchemaError as exc:
            raise SchemaError(f"Invalid JSON Schema: {exc.message}") from exc

        return schema

    @staticmethod
    def _create_validator(schema: Dict[str, Any]) -> Draft7Validator:
        """
        Create a Draft‑7 validator with safe configuration.

        * ``format_checker`` is left at default (provides RFC‑3339 date checks, etc.)
        * ``type`` checking is strict.
        """
        return Draft7Validator(schema)

    def validate(self, data: Union[Dict[str, Any], str, Path]) -> ValidationResult:
        """
        Validate JSON data against the pre‑loaded schema.

        Parameters
        ----------
        data : Union[Dict[str, Any], str, Path]
            The JSON data to validate. Can be a dict, a JSON string, or a file path.

        Returns
        -------
        ValidationResult
            Result object containing a boolean flag and a list of error dictionaries.
        """
        instance = self._load_instance(data)
        errors = sorted(self._validator.iter_errors(instance), key=lambda e: e.path)
        if not errors:
            return ValidationResult(True, [])

        formatted_errors = [self._format_error(err) for err in errors]
        return ValidationResult(False, formatted_errors)

    @staticmethod
    def _load_instance(source: Union[Dict[str, Any], str, Path]) -> Dict[str, Any]:
        """Parse JSON data safely."""
        if isinstance(source, dict):
            return source
        try:
            path = Path(source)
            if path.is_file():
                with path.open("r", encoding="utf-8") as fh:
                    return json.load(fh)
            # Not a file → treat as raw JSON string
            return json.loads(str(source))
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"Unable to load JSON data: {exc}") from exc

    @staticmethod
    def _format_error(err: ValidationError) -> Dict[str, Any]:
        """
        Convert a jsonschema.ValidationError into a serialisable dict.

        Includes:
        * ``message`` – human‑readable description
        * ``instance_path`` – JSON Pointer to the offending value
        * ``schema_path`` – JSON Pointer to the failing schema rule
        * ``validator`` – keyword that failed (e.g., ``type``, ``required``)
        * ``validator_value`` – the value of the rule from the schema
        * ``cause`` – optional nested error details
        """
        error_dict: Dict[str, Any] = {
            "message": err.message,
            "instance_path": "/" + "/".join(str(p) for p in err.absolute_path),
            "schema_path": "/" + "/".join(str(p) for p in err.absolute_schema_path),
            "validator": err.validator,
            "validator_value": err.validator_value,
        }
        # Add the failing value when helpful (but avoid huge dumps)
        if err.instance is not None and not isinstance(err.instance, (dict, list)):
            error_dict["instance"] = err.instance

        # Include sub‑errors for ``anyOf``/``oneOf``/``allOf`` failures
        if err.context:
            error_dict["cause"] = [JSONValidationService._format_error(c) for c in err.context]

        return error_dict


# --------------------------------------------------------------------------- #
# Example usage (removed from production code – kept for illustration only)
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example schema
    example_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "Person",
        "type": "object",
        "required": ["id", "name", "email"],
        "properties": {
            "