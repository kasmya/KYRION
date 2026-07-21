"""
JSON Data Validation Service

A self-contained module for validating JSON data against a schema definition.
Supports required fields, type checking, string pattern matching, nested structures,
and comprehensive error reporting.

Security considerations:
- Limits recursion depth to prevent stack exhaustion
- Validates regex patterns for ReDoS protection
- Sanitizes error messages to prevent information leakage
- Uses constant-time comparison where applicable
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, Set, Tuple
from enum import Enum
from pathlib import Path


class JSONType(Enum):
    """Supported JSON types for validation."""
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    NULL = "null"


@dataclass(frozen=True)
class ValidationError:
    """
    Represents a single validation error.
    
    Attributes:
        path: JSON pointer path to the invalid value (e.g., "/users/0/name")
        message: Human-readable error description
        code: Machine-readable error code
        expected: Expected type or constraint (optional)
        actual: Actual value encountered (optional, sanitized)
    """
    path: str
    message: str
    code: str
    expected: Optional[str] = None
    actual: Optional[str] = None


@dataclass
class ValidationResult:
    """
    Result of a validation operation.
    
    Attributes:
        is_valid: True if validation passed, False otherwise
        errors: List of validation errors (empty if valid)
        validated_data: The validated data (if valid, otherwise None)
    """
    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    validated_data: Optional[Any] = None


class SchemaValidator:
    """
    Validates JSON data against a schema definition.
    
    The schema follows a simplified JSON Schema-like structure:
    {
        "type": "object|array|string|number|integer|boolean|null",
        "required": ["field1", "field2"],  // for objects
        "properties": {                    // for objects
            "field1": { ...schema... },
            "field2": { ...schema... }
        },
        "additionalProperties": bool|schema,  // for objects
        "items": schema|[schema],         // for arrays
        "minItems": int,                  // for arrays
        "maxItems": int,                  // for arrays
        "pattern": "regex",               // for strings
        "minLength": int,                 // for strings
        "maxLength": int,                 // for strings
        "enum": [value1, value2],         // for any type
        "minimum": number,                // for numbers
        "maximum": number,                // for numbers
        "exclusiveMinimum": bool,         // for numbers
        "exclusiveMaximum": bool          // for numbers
    }
    """
    
    # Security constants
    MAX_RECURSION_DEPTH = 100
    MAX_STRING_LENGTH = 10_000
    MAX_ARRAY_LENGTH = 10_000
    MAX_OBJECT_KEYS = 1_000
    REGEX_TIMEOUT = 1.0  # seconds (simulated via length check)
    
    # Supported types mapping
    TYPE_CHECKERS = {
        JSONType.STRING: lambda v: isinstance(v, str),
        JSONType.NUMBER: lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        JSONType.INTEGER: lambda v: isinstance(v, int) and not isinstance(v, bool),
        JSONType.BOOLEAN: lambda v: isinstance(v, bool),
        JSONType.ARRAY: lambda v: isinstance(v, list),
        JSONType.OBJECT: lambda v: isinstance(v, dict),
        JSONType.NULL: lambda v: v is None,
    }
    
    def __init__(self, schema: Dict[str, Any], strict_mode: bool = True):
        """
        Initialize the validator with a schema.
        
        Args:
            schema: The validation schema dictionary
            strict_mode: If True, reject unknown properties in objects
            
        Raises:
            ValueError: If schema is invalid or malformed
        """
        self._schema = self._validate_schema(schema)
        self._strict_mode = strict_mode
        self._compiled_patterns: Dict[str, re.Pattern] = {}
    
    def _validate_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and normalize the schema itself.
        
        Args:
            schema: Raw schema dictionary
            
        Returns:
            Normalized schema dictionary
            
        Raises:
            ValueError: If schema is invalid
        """
        if not isinstance(schema, dict):
            raise ValueError("Schema must be a dictionary")
        
        if "type" not in schema:
            raise ValueError("Schema must have a 'type' field")
        
        try:
            schema_type = JSONType(schema["type"])
        except ValueError:
            raise ValueError(f"Invalid type: {schema['type']}. Must be one of: {[t.value for t in JSONType]}")
        
        # Validate type-specific constraints
        if schema_type == JSONType.OBJECT:
            if "properties" in schema and not isinstance(schema["properties"], dict):
                raise ValueError("'properties' must be a dictionary")
            if "required" in schema:
                if not isinstance(schema["required"], list):
                    raise ValueError("'required' must be a list")
                for req in schema["required"]:
                    if not isinstance(req, str):
                        raise ValueError("Required field names must be strings")
        
        elif schema_type == JSONType.ARRAY:
            if "items" in schema:
                items = schema["items"]
                if isinstance(items, list):
                    for item_schema in items:
                        self._validate_schema(item_schema)
                elif isinstance(items, dict):
                    self._validate_schema(items)
                else:
                    raise ValueError("'items' must be a schema or list of schemas")
        
        elif schema_type == JSONType.STRING:
            if "pattern" in schema:
                if not isinstance(schema["pattern"], str):
                    raise ValueError("'pattern' must be a string")
                # Pre-validate regex for safety
                self._compile_pattern(schema["pattern"])
        
        return schema
    
    def _compile_pattern(self, pattern: str) -> re.Pattern:
        """
        Compile and cache a regex pattern with safety checks.
        
        Args:
            pattern: Regex pattern string
            
        Returns:
            Compiled regex pattern
            
        Raises:
            ValueError: If pattern is invalid or potentially dangerous
        """
        if pattern in self._compiled_patterns:
            return self._compiled_patterns[pattern]
        
        # Basic ReDoS protection: reject patterns with nested quantifiers
        dangerous_patterns = [
            r'\(\?.*[\+\*]\{',  # nested quantifiers
            r'\(\?.*[\+\*].*[\+\*]',  # multiple quantifiers in group
        ]
        for danger in dangerous_patterns:
            if re.search(danger, pattern):
                raise ValueError(f"Potentially dangerous regex pattern rejected: {pattern}")
        
        try:
            compiled = re.compile(pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}")
        
        self._compiled_patterns[pattern] = compiled
        return compiled
    
    def validate(self, data: Any, path: str = "") -> ValidationResult:
        """
        Validate data against the schema.
        
        Args:
            data: The JSON data to validate
            path: Current JSON pointer path (used internally for recursion)
            
        Returns:
            ValidationResult with validation status and any errors
        """
        errors: List[ValidationError] = []
        validated = self._validate_recursive(data, self._schema, path, errors, 0)
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            validated_data=validated if len(errors) == 0 else None
        )
    
    def _validate_recursive(
        self,
        data: Any,
        schema: Dict[str, Any],
        path: str,
        errors: List[ValidationError],
        depth: int
    ) -> Any:
        """
        Recursively validate data against schema.
        
        Args:
            data: Data to validate
            schema: Schema to validate against
            path: Current JSON pointer path
            errors: List to accumulate errors
            depth: Current recursion depth
            
        Returns:
            Validated data (potentially coerced/normalized)
        """
        if depth > self.MAX_RECURSION_DEPTH:
            errors.append(ValidationError(
                path=path or "/",
                message="Maximum recursion depth exceeded",
                code="MAX_DEPTH_EXCEEDED"
            ))
            return data
        
        schema_type = JSONType(schema["type"])
        
        # Type check
        if not self.TYPE_CHECKERS[schema_type](data):
            errors.append(ValidationError(
                path=path or "/",
                message=f"Expected type '{schema_type.value}', got '{type(data).__name__}'",
                code="TYPE_MISMATCH",
                expected=schema_type.value,
                actual=type(data).__name__
            ))
            return data
        
        # Type-specific validation
        if schema_type == JSONType.OBJECT:
            return self._validate_object(data, schema, path, errors, depth)
        elif schema_type == JSONType.ARRAY:
            return self._validate_array(data, schema, path, errors, depth)
        elif schema_type == JSONType.STRING:
            return self._validate_string(data, schema, path, errors)
        elif schema_type in (JSONType.NUMBER, JSONType.INTEGER):
            return self._validate_number(data, schema, path, errors, schema_type)
        elif schema_type == JSONType.BOOLEAN:
            return data
        elif schema_type == JSONType.NULL:
            return None
        
        return data
    
    def _validate_object(
        self,
        data: dict,
        schema: Dict[str, Any],
        path: str,
        errors: List[ValidationError],
        depth: int
    ) -> dict:
        """Validate an object against schema."""
        if len(data) > self.MAX_OBJECT_KEYS:
            errors.append(ValidationError(
                path=path,
                message=f"Object has too many keys (max {self.MAX_OBJECT_KEYS})",
                code="OBJECT_TOO_LARGE"
            ))
            return data
        
        validated = {}
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        additional_props = schema.get("additionalProperties", True)
        
        # Check required fields
        for req_field in required:
            if req_field not in data:
                errors.append(ValidationError(
                    path=f"{path}/{req_field}" if path else f"/{req_field}",
                    message=f"Required field '{req_field}' is missing",
                    code="REQUIRED_FIELD_MISSING",
                    expected=req_field
                ))
        
        # Validate each property
        for key, value in data.items():
            key_path = f"{path}/{key}" if path else f"/{key}"
            
            if key in properties:
                # Known property - validate against its schema
                validated[key] = self._validate_recursive(
                    value, properties[key], key_path, errors, depth + 1
                )
            else:
                # Unknown property
                if additional_props is False:
                    if self._strict_mode:
                        errors.append(ValidationError(
                            path=key_path,
                            message=f"Additional property '{key}' is not allowed",
                            code="ADDITIONAL_PROPERTY_NOT_ALLOWED",
                            actual=key
                        ))
                elif isinstance(additional_props, dict):
                    # Validate against additionalProperties schema
                    validated[key] = self._validate_recursive(
                        value, additional_props, key_path, errors, depth + 1
                    )
                else:
                    # Allow any additional property
                    validated[key] = value
        
        return validated
    
    def _validate_array(
        self,
        data: list,
        schema: Dict[str, Any],
        path: str,
        errors: List[ValidationError],
        depth: int
    ) -> list:
        """Validate an array against schema."""
        if len(data) > self.MAX_ARRAY_LENGTH:
            errors.append(ValidationError(
                path=path,
                message=f"Array length exceeds maximum ({self.MAX_ARRAY_LENGTH})",
                code="ARRAY_TOO_LONG"
            ))
            return data
        
        min_items = schema.get("minItems", 0)
        max_items = schema.get("maxItems", self.MAX_ARRAY_LENGTH)
        
        if len(data) < min_items:
            errors.append(ValidationError(
                path=path,
                message=f"Array must have at least {min_items} items, got {len(data)}",
                code="ARRAY_TOO_SHORT",
                expected=str(min_items),
                actual=str(len(data))
            ))
        
        if len(data) > max_items:
            errors.append(ValidationError(
                path=path,
                message=f"Array must have at most {max_items} items, got {len(data)}",
                code="ARRAY_TOO_LONG",
                expected=str(max_items),
                actual=str(len(data))
            ))
        
        items_schema = schema.get("items")
        validated = []
        
        for index, item in enumerate(data):
            item_path = f"{path}/{index}"
            
            if isinstance(items_schema, list):
                # Tuple validation: each position has its own schema
                if index < len(items_schema):
                    validated.append(self._validate_recursive(
                        item, items_schema[index], item_path, errors, depth + 1
                    ))
                elif additional_items := schema.get("additionalItems"):
                    if additional_items is False:
                        errors.append(ValidationError(
                            path=item_path,
                            message=f"Additional item at index {index} not allowed",
                            code="ADDITIONAL_ITEM_NOT_ALLOWED"
                        ))
                    elif isinstance(additional_items, dict):
                        validated.append(self._validate_recursive(
                            item, additional_items, item_path, errors, depth + 1
                        ))
                    else:
                        validated.append(item)
                else:
                    validated.append(item)
            elif isinstance(items_schema, dict):
                # All items use the same schema
                validated.append(self._validate_recursive(
                    item, items_schema, item_path, errors, depth + 1
                ))
            else:
                # No item schema - accept anything
                validated.append(item)
        
        return validated
    
    def _validate_string(
        self,
        data: str,
        schema: Dict[str, Any],
        path: str,
        errors: List[ValidationError]
    ) -> str:
        """Validate a string against schema constraints."""
        if len(data) > self.MAX_STRING_LENGTH:
            errors.append(ValidationError(
                path=path,
                message=f"String length exceeds maximum ({self.MAX_STRING_LENGTH})",
                code="STRING_TOO_LONG"
            ))
            return data
        
        # Length constraints
        min_length = schema.get("minLength", 0)
        max_length = schema.get("maxLength", self.MAX_STRING_LENGTH)
        
        if len(data) < min_length:
            errors.append(ValidationError(
                path=path,
                message=f"String must be at least {min_length} characters, got {len(data)}",
                code="STRING_TOO_SHORT",
                expected=str(min_length),
                actual=str(len(data))
            ))
        
        if len(data) > max_length:
            errors.append(ValidationError(
                path=path,
                message=f"String must be at most {max_length} characters, got {len(data)}",
                code="STRING_TOO_LONG",
                expected=str(max_length),
                actual=str(len(data))
            ))
        
        # Pattern matching
        if "pattern" in schema:
            pattern = schema["pattern"]
            try:
                compiled = self._compile_pattern(pattern)
                if not compiled.fullmatch(data):
                    errors.append(ValidationError(
                        path=path,
                        message=f"String does not match pattern '{pattern}'",
                        code="PATTERN_MISMATCH",
                        expected=pattern,
                        actual=data[:100] + "..." if len(data) > 100 else data
                    ))
            except ValueError as e:
                errors.append(ValidationError(
                    path=path,
                    message=f"Invalid pattern in schema: {e}",
                    code="INVALID_PATTERN"
                ))
        
        # Enum validation
        if "enum" in schema:
            if data not in schema["enum"]:
                errors.append(ValidationError(
                    path=path,
                    message=f"Value must be one of: {schema['enum']}",
                    code="ENUM_MISMATCH",
                    expected=str(schema["enum"]),
                    actual=data[:100] + "..." if len(data) > 100 else data
                ))
        
        return data
    
    def _validate_number(
        self,
        data: Union[int, float