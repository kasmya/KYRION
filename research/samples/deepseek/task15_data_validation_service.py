"""
Data Validation Service with custom validators and OpenAPI documentation.

Features:
- Validate JSON payloads against dynamic schemas
- Custom validators (email, phone, UUID, credit card)
- Generate OpenAPI documentation automatically
- Detailed error messages with suggestions
- Schema registry and management
"""

import re
import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Union, Type, Set
from enum import Enum
import uuid
from decimal import Decimal

from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import (
    BaseModel, Field, validator, root_validator, conint, confloat,
    constr, conlist, EmailStr, AnyUrl, IPvAnyAddress, create_model
)
import phonenumbers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('validation_service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="Data Validation Service",
    description="Dynamic data validation with custom validators and schema management",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ValidationRule(BaseModel):
    """Base validation rule model."""
    rule_type: str
    params: Optional[Dict[str, Any]] = None

class FieldSchema(BaseModel):
    """Field schema definition."""
    name: str
    type: str = Field(..., description="Field type: string, integer, float, boolean, email, phone, uuid, url")
    required: bool = True
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    pattern: Optional[str] = None
    enum: Optional[List[Any]] = None
    custom_validators: Optional[List[str]] = None

class SchemaDefinition(BaseModel):
    """Schema definition for validation."""
    schema_name: str
    description: Optional[str] = None
    fields: List[FieldSchema]
    version: str = "1.0.0"

class ValidationError(BaseModel):
    """Validation error detail."""
    field: str
    value: Any
    message: str
    suggestion: Optional[str] = None

class ValidationResult(BaseModel):
    """Validation result."""
    is_valid: bool
    schema_name: str
    errors: List[ValidationError] = []
    warnings: List[str] = []
    validated_data: Optional[Dict[str, Any]] = None

class CustomValidators:
    """Collection of custom validation functions."""
    
    @staticmethod
    def validate_email(value: str) -> tuple[bool, str]:
        """
        Validate email address format.
        
        Args:
            value: Email to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        if not re.match(email_pattern, value):
            return False, f"'{value}' is not a valid email address"
        
        # Check for common disposable domains
        disposable_domains = {'tempmail.com', 'throwaway.com', 'mailinator.com'}
        domain = value.split('@')[1].lower()
        
        if domain in disposable_domains:
            return False, f"Disposable email domains are not allowed: {domain}"
        
        return True, ""
    
    @staticmethod
    def validate_phone(value: str, country_code: str = "US") -> tuple[bool, str]:
        """
        Validate phone number using phonenumbers library.
        
        Args:
            value: Phone number to validate
            country_code: ISO country code
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            phone_number = phonenumbers.parse(value, country_code)
            
            if not phonenumbers.is_valid_number(phone_number):
                return False, f"'{value}' is not a valid phone number for {country_code}"
            
            formatted = phonenumbers.format_number(
                phone_number,
                phonenumbers.PhoneNumberFormat.INTERNATIONAL
            )
            
            return True, formatted
            
        except phonenumbers.NumberParseException:
            return False, f"'{value}' could not be parsed as a phone number"
    
    @staticmethod
    def validate_uuid(value: str) -> tuple[bool, str]:
        """
        Validate UUID format.
        
        Args:
            value: UUID string to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            uuid.UUID(value)
            return True, ""
        except (ValueError, AttributeError):
            return False, f"'{value}' is not a valid UUID"
    
    @staticmethod
    def validate_credit_card(value: str) -> tuple[bool, str]:
        """
        Validate credit card number using Luhn algorithm.
        
        Args:
            value: Credit card number
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Remove spaces and dashes
        cleaned = re.sub(r'[\s-]', '', value)
        
        if not cleaned.isdigit():
            return False, "Credit card number must contain only digits"
        
        if len(cleaned) < 13 or len(cleaned) > 19:
            return False, "Credit card number length is invalid"
        
        # Luhn algorithm
        total = 0
        reverse_digits = cleaned[::-1]
        
        for i, digit in enumerate(reverse_digits):
            n = int(digit)
            if i % 2 == 1:
                n *= 2
                if n > 9:
                    n -= 9
            total += n
        
        if total % 10 != 0:
            return False, "Credit card number failed Luhn check"
        
        # Detect card type
        card_type = CustomValidators._detect_card_type(cleaned)
        
        return True, f"Valid {card_type} card"
    
    @staticmethod
    def _detect_card_type(number: str) -> str:
        """Detect credit card type from number."""
        if number.startswith('4'):
            return 'Visa'
        elif number.startswith(('51', '52', '53', '54', '55')):
            return 'Mastercard'
        elif number.startswith(('34', '37')):
            return 'American Express'
        elif number.startswith('6011') or number.startswith('65'):
            return 'Discover'
        else:
            return 'Unknown'
    
    @staticmethod
    def validate_url(value: str) -> tuple[bool, str]:
        """
        Validate URL format.
        
        Args:
            value: URL to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        url_pattern = r'^https?:\/\/(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&\/=]*)$'
        
        if not re.match(url_pattern, value):
            return False, f"'{value}' is not a valid URL"
        
        return True, ""
    
    @staticmethod
    def validate_password_strength(value: str) -> tuple[bool, str]:
        """
        Validate password strength.
        
        Args:
            value: Password to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        checks = []
        
        if len(value) < 8:
            checks.append("be at least 8 characters long")
        if not re.search(r'[A-Z]', value):
            checks.append("contain at least one uppercase letter")
        if not re.search(r'[a-z]', value):
            checks.append("contain at least one lowercase letter")
        if not re.search(r'\d', value):
            checks.append("contain at least one digit")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
            checks.append("contain at least one special character")
        
        if checks:
            return False, f"Password must: {', '.join(checks)}"
        
        return True, "Password meets all requirements"
    
    @staticmethod
    def validate_ip_address(value: str) -> tuple[bool, str]:
        """
        Validate IP address (IPv4 or IPv6).
        
        Args:
            value: IP address to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            IPvAnyAddress.validate(value)
            return True, ""
        except:
            return False, f"'{value}' is not a valid IP address"

class SchemaRegistry:
    """Manages schema definitions and dynamic model creation."""
    
    def __init__(self):
        """Initialize schema registry."""
        self.schemas: Dict[str, SchemaDefinition] = {}
        self._register_default_schemas()
    
    def _register_default_schemas(self) -> None:
        """Register default validation schemas."""
        # User registration schema
        self.register_schema(SchemaDefinition(
            schema_name="user_registration",
            description="User registration validation schema",
            fields=[
                FieldSchema(name="username", type="string", min_length=3, max_length=50, required=True),
                FieldSchema(name="email", type="email", required=True),
                FieldSchema(name="password", type="string", min_length=8, max_length=100, 
                          custom_validators=["password_strength"], required=True),
                FieldSchema(name="phone", type="phone", required=False),
                FieldSchema(name="age", type="integer", min_value=13, max_value=120, required=False),
            ]
        ))
        
        # Product schema
        self.register_schema(SchemaDefinition(
            schema_name="product",
            description="Product data validation schema",
            fields=[
                FieldSchema(name="product_id", type="uuid", required=True),
                FieldSchema(name="name", type="string", min_length=1, max_length=200, required=True),
                FieldSchema(name="price", type="float", min_value=0.01, max_value=999999.99, required=True),
                FieldSchema(name="quantity", type="integer", min_value=0, required=True),
                FieldSchema(name="category", type="string", 
                          enum=["electronics", "clothing", "food", "books", "other"], required=True),
                FieldSchema(name="url", type="url", required=False),
            ]
        ))
        
        # Payment schema
        self.register_schema(SchemaDefinition(
            schema_name="payment",
            description="Payment information validation schema",
            fields=[
                FieldSchema(name="card_number", type="string", custom_validators=["credit_card"], required=True),
                FieldSchema(name="expiry_date", type="string", pattern=r"^(0[1-9]|1[0-2])\/\d{4}$", required=True),
                FieldSchema(name="cvv", type="string", pattern=r"^\d{3,4}$", required=True),
                FieldSchema(name="billing_email", type="email", required=True),
                FieldSchema(name="amount", type="float", min_value=0.01, required=True),
            ]
        ))
    
    def register_schema(self, schema: SchemaDefinition) -> None:
        """
        Register a new validation schema.
        
        Args:
            schema: Schema definition
        """
        self.schemas[schema.schema_name] = schema
        logger.info(f"Schema registered: {schema.schema_name} v{schema.version}")
    
    def get_schema(self, schema_name: str) -> Optional[SchemaDefinition]:
        """
        Get schema by name.
        
        Args:
            schema_name: Schema name
            
        Returns:
            Schema definition or None
        """
        return self.schemas.get(schema_name)
    
    def list_schemas(self) -> List[Dict[str, str]]:
        """List all registered schemas."""
        return [
            {
                'name': name,
                'description': schema.description or '',
                'version': schema.version,
                'fields_count': len(schema.fields)
            }
            for name, schema in self.schemas.items()
        ]

class DataValidator:
    """Main data validation engine."""
    
    def __init__(self, registry: SchemaRegistry):
        """
        Initialize validator.
        
        Args:
            registry: Schema registry instance
        """
        self.registry = registry
    
    def validate(
        self,
        data: Dict[str, Any],
        schema_name: str,
        strict: bool = True
    ) -> ValidationResult:
        """
        Validate data against a schema.
        
        Args:
            data: Data to validate
            schema_name: Schema name to validate against
            strict: If True, reject unknown fields
            
        Returns:
            Validation result
        """
        schema = self.registry.get_schema(schema_name)
        
        if not schema:
            return ValidationResult(
                is_valid=False,
                schema_name=schema_name,
                errors=[ValidationError(
                    field="schema",
                    value=schema_name,
                    message=f"Schema '{schema_name}' not found",
                    suggestion="Check available schemas with /schemas endpoint"
                )]
            )
        
        errors = []
        warnings = []
        validated_data = {}
        
        # Check for unknown fields
        if strict:
            allowed_fields = {field.name for field in schema.fields}
            unknown_fields = set(data.keys()) - allowed_fields
            if unknown_fields:
                warnings.append(f"Unknown fields: {', '.join(unknown_fields)}")
        
        # Validate each field
        for field in schema.fields:
            value = data.get(field.name)
            
            # Check required fields
            if field.required and value is None:
                errors.append(ValidationError(
                    field=field.name,
                    value=None,
                    message=f"Field '{field.name}' is required",
                    suggestion="Provide a value for this required field"
                ))
                continue
            
            # Skip validation for None values on optional fields
            if value is None:
                continue
            
            # Type-specific validation
            type_validators = {
                'string': self._validate_string,
                'integer': self._validate_integer,
                'float': self._validate_float,
                'boolean': self._validate_boolean,
                'email': self._validate_email,
                'phone': self._validate_phone,
                'uuid': self._validate_uuid,
                'url': self._validate_url,
                'ip': self._validate_ip,
            }
            
            validator_func = type_validators.get(field.type)
            
            if validator_func:
                is_valid, error_msg = validator_func(value, field)
                if is_valid:
                    validated_data[field.name] = value
                else:
                    errors.append(ValidationError(
                        field=field.name,
                        value=value,
                        message=error_msg,
                        suggestion=self._get_suggestion(field)
                    ))
            else:
                warnings.append(f"No validator for type: {field.type}")
                validated_data[field.name] = value
            
            # Custom validators
            if field.custom_validators:
                for validator_name in field.custom_validators:
                    custom_validator = getattr(CustomValidators, f"validate_{validator_name}", None)
                    if custom_validator:
                        is_valid, result = custom_validator(value)
                        if not is_valid:
                            errors.append(ValidationError(
                                field=field.name,
                                value=value,
                                message=result
                            ))
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            schema_name=schema_name,
            errors=errors,
            warnings=warnings,
            validated_data=validated_data if not errors else None
        )
    
    def _validate_string(self, value: Any, field: FieldSchema) -> tuple[bool, str]:
        """Validate string field."""
        if not isinstance(value, str):
            return False, f"Expected string, got {type(value).__name__}"
        
        if field.min_length and len(value) < field.min_length:
            return False, f"Must be at least {field.min_length} characters"
        
        if field.max_length and len(value) > field.max_length:
            return False, f"Must be at most {field.max_length} characters"
        
        if field.pattern and not re.match(field.pattern, value):
            return False, f"Does not match required pattern: {field.pattern}"
        
        if field.enum and value not in field.enum:
            return False, f"Must be one of: {', '.join(map(str, field.enum))}"
        
        return True, ""
    
    def _validate_integer(self, value: Any, field: FieldSchema) -> tuple[bool, str]:
        """Validate integer field."""
        try:
            int_value = int(value)
        except (ValueError, TypeError):
            return False, f"Expected integer, got {type(value).__name__}"
        
        if field.min_value is not None and int_value < field.min_value:
            return False, f"Must be at least {int(field.min_value)}"
        
        if field.max_value is not None and int_value > field.max_value:
            return False, f"Must be at most {int(field.max_value)}"
        
        return True, ""
    
    def _validate_float(self, value: Any, field: FieldSchema) -> tuple[bool, str]:
        """Validate float field."""
        try:
            float_value = float(value)
        except (ValueError, TypeError):
            return False, f"Expected float, got {type(value).__name__}"
        
        if field.min_value is not None and float_value < field.min_value:
            return False, f"Must be at least {field.min_value}"
        
        if field.max_value is not None and float_value > field.max_value:
            return False, f"Must be at most {field.max_value}"
        
        return True, ""
    
    def _validate_boolean(self, value: Any, field: FieldSchema) -> tuple[bool, str]:
        """Validate boolean field."""
        if not isinstance(value, bool):
            return False, f"Expected boolean, got {type(value).__name__}"
        return True, ""
    
    def _validate_email(self, value: Any, field: FieldSchema) -> tuple[bool, str]:
        """Validate email field."""
        if not isinstance(value, str):
            return False, f"Expected string, got {type(value).__name__}"
        return CustomValidators.validate_email(value)
    
    def _validate_phone(self, value: Any, field: FieldSchema) -> tuple[bool, str]:
        """Validate phone field."""
        if not isinstance(value, str):
            return False, f"Expected string, got {type(value).__name__}"
        return CustomValidators.validate_phone(value)
    
    def _validate_uuid(self, value: Any, field: FieldSchema) -> tuple[bool, str]:
        """Validate UUID field."""
        if not isinstance(value, str):
            return False, f"Expected string, got {type(value).__name__}"
        return CustomValidators.validate_uuid(value)
    
    def _validate_url(self, value: Any, field: FieldSchema) -> tuple[bool, str]:
        """Validate URL field."""
        if not isinstance(value, str):
            return False, f"Expected string, got {type(value).__name__}"
        return CustomValidators.validate_url(value)
    
    def _validate_ip(self, value: Any, field: FieldSchema) -> tuple[bool, str]:
        """Validate IP address field."""
        if not isinstance(value, str):
            return False, f"Expected string, got {type(value).__name__}"
        return CustomValidators.validate_ip_address(value)
    
    def _get_suggestion(self, field: FieldSchema) -> Optional[str]:
        """Get helpful suggestion for field."""
        suggestions = []
        
        if field.type == 'string':
            if field.min_length and field.max_length:
                suggestions.append(f"Provide a string between {field.min_length}-{field.max_length} characters")
            if field.pattern:
                suggestions.append(f"Match pattern: {field.pattern}")
            if field.enum:
                suggestions.append(f"Choose from: {', '.join(map(str, field.enum))}")
        elif field.type in ['integer', 'float']:
            if field.min_value is not None and field.max_value is not None:
                suggestions.append(f"Provide a number between {field.min_value}-{field.max_value}")
        
        return '. '.join(suggestions) if suggestions else None

# Initialize registry and validator
registry = SchemaRegistry()
validator = DataValidator(registry)

@app.get("/")
async def root():
    """API root."""
    return {
        "service": "Data Validation Service",
        "version": "1.0.0",
        "schemas": len(registry.schemas)
    }

@app.post("/validate/{schema_name}", response_model=ValidationResult)
async def validate_data(
    schema_name: str,
    data: Dict[str, Any] = Body(..., description="Data to validate"),
    strict: bool = Query(True, description="Reject unknown fields")
) -> ValidationResult:
    """
    Validate data against a registered schema.
    
    Args:
        schema_name: Schema name to validate against
        data: JSON data to validate
        strict: If True, warn about unknown fields
        
    Returns:
        Validation result with errors and validated data
    """
    try:
        result = validator.validate(data, schema_name, strict)
        
        if result.errors:
            logger.warning(f"Validation failed for {schema_name}: {len(result.errors)} errors")
        else:
            logger.info(f"Validation passed for {schema_name}")
        
        return result
        
    except Exception as e:
        logger.error(f"Validation error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal validation error"
        )

@app.post("/schemas", response_model=SchemaDefinition)
async def register_schema(schema: SchemaDefinition):
    """
    Register a new validation schema.
    
    Args:
        schema: Schema definition
        
    Returns:
        Registered schema
    """
    try:
        registry.register_schema(schema)
        return schema
    except Exception as e:
        logger.error(f"Schema registration error: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to register schema: {str(e)}"
        )

@app.get("/schemas")
async def list_schemas():
    """List all registered schemas."""
    return registry.list_schemas()

@app.get("/schemas/{schema_name}")
async def get_schema(schema_name: str):
    """
    Get schema definition.
    
    Args:
        schema_name: Schema name
        
    Returns:
        Schema definition
    """
    schema = registry.get_schema(schema_name)
    if not schema:
        raise HTTPException(status_code=404, detail=f"Schema '{schema_name}' not found")
    return schema

@app.delete("/schemas/{schema_name}")
async def delete_schema(schema_name: str):
    """
    Delete a schema.
    
    Args:
        schema_name: Schema name to delete
        
    Returns:
        Success message
    """
    if schema_name not in registry.schemas:
        raise HTTPException(status_code=404, detail=f"Schema '{schema_name}' not found")
    
    del registry.schemas[schema_name]
    return {"message": f"Schema '{schema_name}' deleted"}

@app.post("/validate/custom")
async def validate_custom(data: Dict[str, Any] = Body(...)):
    """
    Validate data with custom rules on-the-fly.
    
    Args:
        data: Data with validation rules
        
    Returns:
        Validation results for each field
    """
    results = {}
    
    for field_name, value in data.items():
        if field_name.startswith('_'):
            continue
        
        field_results = []
        
        # Email check
        if 'email' in field_name.lower():
            is_valid, msg = CustomValidators.validate_email(str(value))
            field_results.append({'check': 'email', 'valid': is_valid, 'message': msg})
        
        # Phone check
        if 'phone' in field_name.lower():
            is_valid, msg = CustomValidators.validate_phone(str(value))
            field_results.append({'check': 'phone', 'valid': is_valid, 'message': msg})
        
        # UUID check
        if 'uuid' in field_name.lower() or 'id' in field_name.lower():
            is_valid, msg = CustomValidators.validate_uuid(str(value))
            field_results.append({'check': 'uuid', 'valid': is_valid, 'message': msg})
        
        if field_results:
            results[field_name] = field_results
    
    return results

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005, reload=True)
