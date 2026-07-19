"""
Email validation function - Fixed version (no dead code)
"""

import re
from typing import Tuple, Union


def validate_email(email: Union[str, None]) -> Tuple[bool, str]:
    """
    Validate a user's email address.

    Args:
        email (str): The email address to validate.

    Returns:
        Tuple[bool, str]:
            - True and success message if valid.
            - False and an error message if invalid.
    """
    # Check if input is None
    if email is None:
        return False, "Email cannot be None."

    # Ensure the input is a string
    if not isinstance(email, str):
        return False, "Email must be a string."

    # Remove leading/trailing whitespace
    email = email.strip()

    # Check if the email is empty
    if not email:
        return False, "Email address cannot be empty."

    # Regular expression for basic email validation
    email_pattern = (
        r"^[A-Za-z0-9._%+-]+"
        r"@[A-Za-z0-9.-]+"
        r"\.[A-Za-z]{2,}$"
    )

    if not re.fullmatch(email_pattern, email):
        return False, "Invalid email format."

    # Additional validation checks
    local_part, domain = email.rsplit("@", 1)

    if ".." in email:
        return False, "Email cannot contain consecutive dots."

    if domain.startswith("-") or domain.endswith("-"):
        return False, "Domain cannot start or end with a hyphen."

    if domain.startswith(".") or domain.endswith("."):
        return False, "Domain cannot start or end with a dot."

    return True, "Email address is valid."


# Example usage
if __name__ == "__main__":
    test_emails = [
        "user@example.com",
        "john.doe+test@gmail.com",
        "invalid-email",
        "user@domain",
        "user..name@example.com",
        "",
        None,
        12345,  # Non-string input
    ]

    for email in test_emails:
        valid, message = validate_email(email)
        print(f"{email!r}: {valid} - {message}")
