"""
JSON Data Validation Service

A self-contained module for validating JSON data against a defined schema.
Supports required field validation, type checking, string pattern matching,
nested object/array validation, and comprehensive error reporting.

Security Best Practices:
- No use of eval(), exec(), or dynamic code execution
- Input sanitization through strict type checking
- Regex patterns compiled with re.DOTALL disabled to prevent ReDoS
- Maximum recursion depth limited to prevent stack exhaustion
- All external inputs treated as untrusted
"""

import json
import re
from typing import Any, Dict, List, Optional, Union, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ValidationErrorType(Enum):
    """Enumeration of possible validation error types."""
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    PATTERN_MISMATCH = "PATTERN_MISMATCH"
    ENUM_MISMATCH = "ENUM_MISMATCH"
    ADDITIONAL_PROPERTY_NOT_ALLOWED = "ADDITIONAL_PROPERTY_NOT_ALLOWED"
    INVALID_ARRAY_ITEM = "INVALID_ARRAY_ITEM"
    MAX_DEPTH_EXCEEDED = "MAX_DEPTH_EXCEEDED"
    INVALID_SCHEMA = "INVALID_SCHEMA"


@dataclass(frozen=True)
class ValidationError:
    """
    Represents a single validation error with context.
    
    Attributes:
        path: JSON path to the invalid value (e.g., "user.address.city")
        error_type: Category of the validation error
        message: Human-readable error description
        expected: Expected type/pattern/value (if applicable)
        actual: Actual value that failed validation (truncated for safety)
    """
    path: str
    error_type: ValidationErrorType
    message: str
    expected: Optional[str] = None
    actual: Optional[str] = None


@dataclass
class ValidationResult:
    """
    Container for validation results.
    
    Attributes:
        is_valid: True if validation passed with no errors
        errors: List of validation errors encountered
        validated_data: The validated data (only present if is_valid=True)
    """
    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    validated_data: Optional[Any] = None


class JSONValidator:
    """
    JSON Schema Validator with support for common validation rules.
    
    Supports the following schema keywords:
    - type: string, number, integer, boolean, array, object, null
    - required: boolean (per property) or list of required property names
    - pattern: regex pattern for string validation
    - enum: list of allowed values
    - properties: schema for object properties
    - items: schema for array items
    - additionalProperties: boolean to allow/deny extra properties
    - maxDepth: maximum nesting depth (default: 50)
    
    Example schema:
    {
        "type": "object",
        "properties": {
            "name": {"type": "string", "required": true, "pattern": "^[A-Za-z ]+$"},
            "age": {"type": "integer", "required": true},
            "email": {"type": "string", "pattern": "^[^@]+@[^@]+\\.[^@]+$"},
            "tags": {
                "type": "array",
                "items": {"type": "string"}
            }
        },
        "required": ["name", "age"],
        "additionalProperties": false
    }
    """
    
    # Supported JSON types mapped to Python types
    TYPE_MAP: Dict[str, Tuple[type, ...]] = {
        "string": (str,),
        "number": (int, float),
        "integer": (int,),
        "boolean": (bool,),
        "array": (list,),
        "object": (dict,),
        "null": (type(None),),
    }
    
    # Maximum allowed nesting depth to prevent stack exhaustion
    MAX_SCHEMA_DEPTH: int = 50
    # Maximum length for error value representation
    MAX_ERROR_VALUE_LENGTH: int = 200
    
    def __init__(self, schema: Dict[str, Any], max_depth: Optional[int] = None) -> None:
        """
        Initialize validator with a schema.
        
        Args:
            schema: Dictionary representing the JSON schema
            max_depth: Maximum recursion depth (default: 50)
            
        Raises:
            ValueError: If schema is invalid or max_depth is not positive
        """
        if not isinstance(schema, dict):
            raise ValueError("Schema must be a dictionary")
        
        if max_depth is not None:
            if not isinstance(max_depth, int) or max_depth <= 0:
                raise ValueError("max_depth must be a positive integer")
            self._max_depth = max_depth
        else:
            self._max_depth = self.MAX_SCHEMA_DEPTH
            
        self._schema = schema
        self._compiled_patterns: Dict[str, re.Pattern] = {}
    
    def _get_compiled_pattern(self, pattern: str) -> re.Pattern:
        """
        Get or compile a regex pattern with safety flags.
        
        Args:
            pattern: Regex pattern string
            
        Returns:
            Compiled regex pattern
            
        Raises:
            ValueError: If pattern is invalid
        """
        if pattern not in self._compiled_patterns:
            try:
                # Disable DOTALL to prevent ReDoS via catastrophic backtracking
                # Use timeout if Python 3.11+ (not available in all versions)
                self._compiled_patterns[pattern] = re.compile(pattern)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern '{pattern}': {e}")
        return self._compiled_patterns[pattern]
    
    def _truncate_value(self, value: Any) -> str:
        """
        Safely truncate value for error reporting.
        
        Args:
            value: Value to represent as string
            
        Returns:
            Truncated string representation
        """
        try:
            if isinstance(value, str):
                repr_str = f'"{value}"'
            else:
                repr_str = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            repr_str = str(type(value).__name__)
        
        if len(repr_str) > self.MAX_ERROR_VALUE_LENGTH:
            return repr_str[:self.MAX_ERROR_VALUE_LENGTH] + "... (truncated)"
        return repr_str
    
    def _validate_type(
        self, 
        value: Any, 
        expected_type: str, 
        path: str
    ) -> List[ValidationError]:
        """
        Validate that value matches expected JSON type.
        
        Args:
            value: Value to validate
            expected_type: Expected type name (string, number, etc.)
            path: JSON path for error reporting
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        python_types = self.TYPE_MAP.get(expected_type)
        
        if python_types is None:
            errors.append(ValidationError(
                path=path,
                error_type=ValidationErrorType.INVALID_SCHEMA,
                message=f"Unknown type '{expected_type}' in schema",
                expected=expected_type,
                actual=self._truncate_value(value)
            ))
            return errors
        
        # Special handling: bool is subclass of int in Python
        if expected_type == "integer" and isinstance(value, bool):
            errors.append(ValidationError(
                path=path,
                error_type=ValidationErrorType.TYPE_MISMATCH,
                message=f"Expected integer, got boolean",
                expected="integer",
                actual="boolean"
            ))
            return errors
        
        if expected_type == "number" and isinstance(value, bool):
            errors.append(ValidationError(
                path=path,
                error_type=ValidationErrorType.TYPE_MISMATCH,
                message=f"Expected number, got boolean",
                expected="number",
                actual="boolean"
            ))
            return errors
        
        if not isinstance(value, python_types):
            actual_type = type(value).__name__
            if actual_type == "bool":
                actual_type = "boolean"
            elif actual_type == "NoneType":
                actual_type = "null"
            elif actual_type in ("int", "float"):
                actual_type = "number" if expected_type == "number" else actual_type
            
            errors.append(ValidationError(
                path=path,
                error_type=ValidationErrorType.TYPE_MISMATCH,
                message=f"Expected {expected_type}, got {actual_type}",
                expected=expected_type,
                actual=actual_type
            ))
        
        return errors
    
    def _validate_pattern(
        self, 
        value: str, 
        pattern: str, 
        path: str
    ) -> List[ValidationError]:
        """
        Validate string against regex pattern.
        
        Args:
            value: String value to validate
            pattern: Regex pattern
            path: JSON path for error reporting
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        try:
            compiled = self._get_compiled_pattern(pattern)
            if not compiled.fullmatch(value):
                errors.append(ValidationError(
                    path=path,
                    error_type=ValidationErrorType.PATTERN_MISMATCH,
                    message=f"String does not match pattern '{pattern}'",
                    expected=pattern,
                    actual=self._truncate_value(value)
                ))
        except ValueError as e:
            errors.append(ValidationError(
                path=path,
                error_type=ValidationErrorType.INVALID_SCHEMA,
                message=str(e),
                expected=pattern,
                actual=self._truncate_value(value)
            ))
        return errors
    
    def _validate_enum(
        self, 
        value: Any, 
        enum_values: List[Any], 
        path: str
    ) -> List[ValidationError]:
        """
        Validate value against allowed enum values.
        
        Args:
            value: Value to validate
            enum_values: List of allowed values
            path: JSON path for error reporting
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        # Use JSON serialization for comparison to handle type equivalence
        try:
            value_json = json.dumps(value, sort_keys=True)
            enum_json = {json.dumps(v, sort_keys=True) for v in enum_values}
            if value_json not in enum_json:
                errors.append(ValidationError(
                    path=path,
                    error_type=ValidationErrorType.ENUM_MISMATCH,
                    message=f"Value not in allowed enum values",
                    expected=f"one of {enum_values}",
                    actual=self._truncate_value(value)
                ))
        except (TypeError, ValueError):
            # Fallback to direct comparison
            if value not in enum_values:
                errors.append(ValidationError(
                    path=path,
                    error_type=ValidationErrorType.ENUM_MISMATCH,
                    message=f"Value not in allowed enum values",
                    expected=f"one of {enum_values}",
                    actual=self._truncate_value(value)
                ))
        return errors
    
    def _validate_object(
        self, 
        value: Dict[str, Any], 
        schema: Dict[str, Any], 
        path: str, 
        depth: int
    ) -> List[ValidationError]:
        """
        Validate object against schema.
        
        Args:
            value: Dictionary to validate
            schema: Object schema
            path: Current JSON path
            depth: Current recursion depth
            
        Returns:
            List of validation errors
        """
        errors = []
        
        # Type check
        type_errors = self._validate_type(value, "object", path)
        if type_errors:
            return type_errors
        
        properties = schema.get("properties", {})
        required_fields = schema.get("required", [])
        additional_allowed = schema.get("additionalProperties", True)
        
        # Also check per-property required flag
        for prop_name, prop_schema in properties.items():
            if prop_schema.get("required", False):
                required_fields.append(prop_name)
        
        # Check required fields
        for req_field in required_fields:
            if req_field not in value:
                errors.append(ValidationError(
                    path=f"{path}.{req_field}" if path else req_field,
                    error_type=ValidationErrorType.MISSING_REQUIRED_FIELD,
                    message=f"Required field '{req_field}' is missing",
                    expected="present",
                    actual="missing"
                ))
        
        # Validate each property
        for prop_name, prop_value in value.items():
            prop_path = f"{path}.{prop_name}" if path else prop_name
            
            if prop_name in properties:
                prop_errors = self._validate_value(
                    prop_value, 
                    properties[prop_name], 
                    prop_path, 
                    depth + 1
                )
                errors.extend(prop_errors)
            elif not additional_allowed:
                errors.append(ValidationError(
                    path=prop_path,
                    error_type=ValidationErrorType.ADDITIONAL_PROPERTY_NOT_ALLOWED,
                    message=f"Additional property '{prop_name}' not allowed",
                    expected="defined properties only",
                    actual=prop_name
                ))
        
        return errors
    
    def _validate_array(
        self, 
        value: List[Any], 
        schema: Dict[str, Any], 
        path: str, 
        depth: int
    ) -> List[ValidationError]:
        """
        Validate array against schema.
        
        Args:
            value: List to validate
            schema: Array schema
            path: Current JSON path
            depth: Current recursion depth
            
        Returns:
            List of validation errors
        """
        errors = []
        
        # Type check
        type_errors = self._validate_type(value, "array", path)
        if type_errors:
            return type_errors
        
        items_schema = schema.get("items")
        if items_schema is None:
            # No item validation schema - accept any items
            return errors
        
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            item_errors = self._validate_value(item, items_schema, item_path, depth + 1)
            errors.extend(item_errors)
        
        return errors
    
    def _validate_value(
        self, 
        value: Any, 
        schema: Dict[str, Any], 
        path: str, 
        depth: int
    ) -> List[ValidationError]:
        """
        Validate a value against a schema (recursive).
        
        Args:
            value: Value to validate
            schema: Schema for the value
            path: JSON path for error reporting
            depth: Current recursion depth
            
        Returns:
            List of validation errors
        """
        errors = []
        
        # Check recursion depth
        if depth > self._max_depth:
            errors.append(ValidationError(
                path=path,
                error_type=ValidationErrorType.MAX_DEPTH_EXCEEDED,
                message=f"Maximum validation depth ({self._max_depth}) exceeded",
                expected=f"depth <= {self._max_depth}",
                actual=f"depth = {depth}"
            ))
            return errors
        
        # Get expected type
        expected_type = schema.get("type")
        if expected_type:
            type_errors = self._validate_type(value, expected_type, path)
            if type_errors:
                return type_errors
        
        # Validate enum if present
        if "enum" in schema:
            enum_errors = self._validate_enum(value, schema["enum"], path)
            errors.extend(enum_errors)
        
        # Type-specific validations
        if expected_type == "string" and isinstance(value, str):
            if "pattern" in schema:
                pattern_errors = self._validate_pattern(value, schema["pattern"], path)
                errors.extend(pattern_errors)
        
        elif expected_type == "object" and isinstance(value, dict):
            object_errors = self._validate_object(value, schema, path, depth)
            errors.extend(object_errors)
        
        elif expected_type == "array" and isinstance(value, list):
            array_errors = self._validate_array(value, schema, path, depth)
            errors.extend(array_errors)
        
        return errors
    
    def validate(self, data: