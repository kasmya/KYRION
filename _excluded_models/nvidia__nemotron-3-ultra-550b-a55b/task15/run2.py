"""
JSON Data Validation Service

A comprehensive JSON validation module that provides schema-based validation
with detailed error reporting. Supports required fields, type checking,
pattern matching, and custom validation rules.

This module follows security best practices by:
- Using safe JSON parsing (no eval/exec)
- Validating schema structure before use
- Limiting recursion depth
- Sanitizing error messages to prevent information leakage
"""

import json
import re
from typing import Any, Dict, List, Optional, Union, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import logging

# Configure module logger
logger = logging.getLogger(__name__)


class ValidationErrorType(Enum):
    """Enumeration of validation error types."""
    MISSING_REQUIRED_FIELD = "missing_required_field"
    TYPE_MISMATCH = "type_mismatch"
    PATTERN_MISMATCH = "pattern_mismatch"
    ENUM_MISMATCH = "enum_mismatch"
    MIN_LENGTH_VIOLATION = "min_length_violation"
    MAX_LENGTH_VIOLATION = "max_length_violation"
    MINIMUM_VIOLATION = "minimum_violation"
    MAXIMUM_VIOLATION = "maximum_violation"
    INVALID_FORMAT = "invalid_format"
    ADDITIONAL_PROPERTIES = "additional_properties"
    SCHEMA_ERROR = "schema_error"
    CUSTOM_VALIDATION_FAILED = "custom_validation_failed"


@dataclass(frozen=True)
class ValidationError:
    """
    Represents a single validation error with detailed context.
    
    Attributes:
        path: JSON path to the invalid value (e.g., "user.address.city")
        error_type: Category of the validation error
        message: Human-readable error description
        expected: Expected value or constraint (if applicable)
        actual: Actual value that failed validation (if applicable)
        schema_path: Path within the schema that triggered the error
    """
    path: str
    error_type: ValidationErrorType
    message: str
    expected: Optional[Any] = None
    actual: Optional[Any] = None
    schema_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for JSON serialization."""
        result = {
            "path": self.path,
            "error_type": self.error_type.value,
            "message": self.message
        }
        if self.expected is not None:
            result["expected"] = self.expected
        if self.actual is not None:
            result["actual"] = self.actual
        if self.schema_path is not None:
            result["schema_path"] = self.schema_path
        return result


@dataclass
class ValidationResult:
    """
    Container for validation results.
    
    Attributes:
        is_valid: True if validation passed, False otherwise
        errors: List of validation errors (empty if valid)
        validated_data: The validated data (may include defaults/coercion)
    """
    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    validated_data: Optional[Any] = None

    def add_error(self, error: ValidationError) -> None:
        """Add an error and mark result as invalid."""
        self.errors.append(error)
        self.is_valid = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for JSON serialization."""
        return {
            "is_valid": self.is_valid,
            "errors": [error.to_dict() for error in self.errors],
            "validated_data": self.validated_data
        }


class JSONValidator:
    """
    JSON Schema Validator with comprehensive validation capabilities.
    
    Supports JSON Schema Draft 7 features including:
    - Required fields validation
    - Type checking (string, number, integer, boolean, array, object, null)
    - String pattern matching (regex)
    - Enum validation
    - Length constraints (minLength, maxLength)
    - Numeric constraints (minimum, maximum, exclusiveMinimum, exclusiveMaximum)
    - Format validation (email, uri, date-time, etc.)
    - Additional properties control
    - Nested object and array validation
    
    Example:
        >>> schema = {
        ...     "type": "object",
        ...     "properties": {
        ...         "name": {"type": "string", "minLength": 1},
        ...         "age": {"type": "integer", "minimum": 0}
        ...     },
        ...     "required": ["name"]
        ... }
        >>> validator = JSONValidator(schema)
        >>> result = validator.validate({"name": "John", "age": 30})
        >>> result.is_valid
        True
    """
    
    # Supported JSON Schema types
    JSON_TYPES = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None)
    }
    
    # Built-in format validators
    FORMAT_VALIDATORS = {
        "email": re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'),
        "uri": re.compile(r'^[a-zA-Z][a-zA-Z0-9+.-]*://.+'),
        "date-time": re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$'),
        "date": re.compile(r'^\d{4}-\d{2}-\d{2}$'),
        "time": re.compile(r'^\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$'),
        "uuid": re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$', re.IGNORECASE),
        "ipv4": re.compile(r'^(\d{1,3}\.){3}\d{1,3}$'),
        "ipv6": re.compile(r'^([0-9a-f]{1,4}:){7}[0-9a-f]{1,4}$', re.IGNORECASE),
        "hostname": re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'),
        "json-pointer": re.compile(r'^(/([^/~]|~[01])*)*$'),
        "regex": re.compile(r'^.*$')  # Any string is valid regex pattern (validated at use)
    }
    
    # Maximum recursion depth to prevent stack exhaustion
    MAX_RECURSION_DEPTH = 100
    
    def __init__(
        self,
        schema: Dict[str, Any],
        *,
        strict_mode: bool = True,
        allow_additional_properties: bool = False,
        custom_format_validators: Optional[Dict[str, re.Pattern]] = None,
        max_errors: int = 50
    ) -> None:
        """
        Initialize the validator with a JSON schema.
        
        Args:
            schema: JSON schema dictionary (Draft 7 compatible)
            strict_mode: If True, enforce all schema constraints strictly
            allow_additional_properties: If True, ignore additionalProperties: false
            custom_format_validators: Additional format validators (name -> regex pattern)
            max_errors: Maximum number of errors to collect before stopping
            
        Raises:
            ValueError: If schema is invalid or cannot be parsed
            TypeError: If schema is not a dictionary
        """
        if not isinstance(schema, dict):
            raise TypeError(f"Schema must be a dictionary, got {type(schema).__name__}")
        
        self._schema = schema
        self._strict_mode = strict_mode
        self._allow_additional_properties = allow_additional_properties
        self._max_errors = max_errors
        self._format_validators = dict(self.FORMAT_VALIDATORS)
        
        if custom_format_validators:
            for name, pattern in custom_format_validators.items():
                if not isinstance(pattern, re.Pattern):
                    raise TypeError(f"Custom format validator '{name}' must be a compiled regex pattern")
                self._format_validators[name] = pattern
        
        # Validate schema structure
        self._validate_schema(self._schema)
        logger.debug("JSONValidator initialized with schema: %s", json.dumps(schema)[:200])
    
    def _validate_schema(self, schema: Dict[str, Any], depth: int = 0) -> None:
        """
        Validate schema structure for basic correctness.
        
        Args:
            schema: Schema to validate
            depth: Current recursion depth
            
        Raises:
            ValueError: If schema is malformed
            RecursionError: If schema exceeds maximum recursion depth
        """
        if depth > self.MAX_RECURSION_DEPTH:
            raise RecursionError(f"Schema exceeds maximum recursion depth of {self.MAX_RECURSION_DEPTH}")
        
        if not isinstance(schema, dict):
            raise ValueError("Schema must be a JSON object")
        
        # Validate type field if present
        if "type" in schema:
            type_val = schema["type"]
            if isinstance(type_val, str):
                if type_val not in self.JSON_TYPES:
                    raise ValueError(f"Unknown type: {type_val}")
            elif isinstance(type_val, list):
                for t in type_val:
                    if t not in self.JSON_TYPES:
                        raise ValueError(f"Unknown type in array: {t}")
            else:
                raise ValueError("Type must be string or array of strings")
        
        # Recursively validate nested schemas
        for key in ("properties", "patternProperties", "dependencies"):
            if key in schema and isinstance(schema[key], dict):
                for prop_schema in schema[key].values():
                    if isinstance(prop_schema, dict):
                        self._validate_schema(prop_schema, depth + 1)
        
        if "items" in schema:
            items = schema["items"]
            if isinstance(items, dict):
                self._validate_schema(items, depth + 1)
            elif isinstance(items, list):
                for item_schema in items:
                    if isinstance(item_schema, dict):
                        self._validate_schema(item_schema, depth + 1)
        
        for key in ("additionalProperties", "additionalItems", "contains", "not", "if", "then", "else"):
            if key in schema and isinstance(schema[key], dict):
                self._validate_schema(schema[key], depth + 1)
        
        for key in ("allOf", "anyOf", "oneOf"):
            if key in schema and isinstance(schema[key], list):
                for sub_schema in schema[key]:
                    if isinstance(sub_schema, dict):
                        self._validate_schema(sub_schema, depth + 1)
    
    def validate(self, data: Any, *, path: str = "$") -> ValidationResult:
        """
        Validate data against the schema.
        
        Args:
            data: Data to validate (parsed JSON: dict, list, str, int, float, bool, None)
            path: JSON path prefix for error reporting (default: "$")
            
        Returns:
            ValidationResult containing validation status and any errors
        """
        result = ValidationResult(is_valid=True)
        try:
            validated = self._validate_recursive(data, self._schema, path, result, 0)
            result.validated_data = validated
        except RecursionError:
            result.add_error(ValidationError(
                path=path,
                error_type=ValidationErrorType.SCHEMA_ERROR,
                message="Validation exceeded maximum recursion depth"
            ))
        except Exception as e:
            logger.exception("Unexpected error during validation")
            result.add_error(ValidationError(
                path=path,
                error_type=ValidationErrorType.SCHEMA_ERROR,
                message=f"Internal validation error: {type(e).__name__}"
            ))
        return result
    
    def validate_json_string(self, json_string: str, *, path: str = "$") -> ValidationResult:
        """
        Validate a JSON string against the schema.
        
        Args:
            json_string: JSON string to parse and validate
            path: JSON path prefix for error reporting
            
        Returns:
            ValidationResult containing validation status and any errors
        """
        try:
            data = json.loads(json_string)
        except json.JSONDecodeError as e:
            result = ValidationResult(is_valid=False)
            result.add_error(ValidationError(
                path=path,
                error_type=ValidationErrorType.INVALID_FORMAT,
                message=f"Invalid JSON: {e.msg}",
                expected="valid JSON",
                actual=json_string[:100] + "..." if len(json_string) > 100 else json_string
            ))
            return result
        
        return self.validate(data, path=path)
    
    def _validate_recursive(
        self,
        data: Any,
        schema: Dict[str, Any],
        path: str,
        result: ValidationResult,
        depth: int
    ) -> Any:
        """
        Recursively validate data against schema.
        
        Args:
            data: Data to validate
            schema: Schema to validate against
            path: Current JSON path
            result: Result accumulator
            depth: Current recursion depth
            
        Returns:
            Validated/coerced data
        """
        if depth > self.MAX_RECURSION_DEPTH:
            raise RecursionError("Maximum recursion depth exceeded")
        
        if len(result.errors) >= self._max_errors:
            return data
        
        # Handle $ref (simplified - no external refs)
        if "$ref" in schema:
            # In a full implementation, this would resolve references
            # For now, we skip ref validation
            pass
        
        # Type validation
        if "type" in schema:
            if not self._check_type(data, schema["type"], path, result, schema):
                return data
        
        # Enum validation
        if "enum" in schema:
            self._validate_enum(data, schema["enum"], path, result)
        
        # Const validation
        if "const" in schema:
            self._validate_const(data, schema["const"], path, result)
        
        # String validations
        if isinstance(data, str):
            self._validate_string(data, schema, path, result)
        
        # Numeric validations
        if isinstance(data, (int, float)) and not isinstance(data, bool):
            self._validate_number(data, schema, path, result)
        
        # Array validations
        if isinstance(data, list):
            data = self._validate_array(data, schema, path, result, depth)
        
        # Object validations
        if isinstance(data, dict):
            data = self._validate_object(data, schema, path, result, depth)
        
        # Format validation
        if "format" in schema and isinstance(data, str):
            self._validate_format(data, schema["format"], path, result)
        
        # Combined schemas
        if "allOf" in schema:
            for i, sub_schema in enumerate(schema["allOf"]):
                self._validate_recursive(data, sub_schema, f"{path}/allOf/{i}", result, depth + 1)
        
        if "anyOf" in schema:
            self._validate_any_of(data, schema["anyOf"], path, result, depth)
        
        if "oneOf" in schema:
            self._validate_one_of(data, schema["oneOf"], path, result, depth)
        
        if "not" in schema:
            self._validate_not(data, schema["not"], path, result, depth)
        
        if "if" in schema:
            self._validate_conditional(data, schema, path, result, depth)
        
        return data
    
    def _check_type(
        self,
        data: Any,
        expected_type: Union[str, List[str]],
        path: str,
        result: ValidationResult,
        schema: Dict[str, Any]
    ) -> bool:
        """Check if data matches expected type(s)."""
        types = [expected_type] if isinstance(expected_type, str) else expected_type
        
        for type_name in types:
            if type_name not in self.JSON_TYPES:
                result.add_error(ValidationError(
                    path=path,
                    error_type=ValidationErrorType.SCHEMA_ERROR,
                    message=f"Unknown type in schema: {type_name}",
                    schema_path=schema.get("$id", "")
                ))
                continue
            
            expected = self.JSON_TYPES[type_name]
            if isinstance(expected, tuple):
                if isinstance(data, expected):
                    return True
            elif isinstance(data, expected):
                return True
        
        # Type mismatch
        actual_type = type(data).__name__
        if data is None:
            actual_type = "null"
        elif isinstance(data, bool):
            actual_type = "boolean"
        elif isinstance(data, int):
            actual_type = "integer"
        elif isinstance(data, float):
            actual_type = "number"
        
        result.add_error(ValidationError(
            path=path,
            error_type=ValidationErrorType.TYPE_MISMATCH,
            message=f"Expected type {types}, got {actual_type}",
            expected=types if len(types) > 1 else types[0],
            actual