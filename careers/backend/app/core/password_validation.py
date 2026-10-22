import re

COMMON_WEAK_PASSWORDS = {
    "password",
    "12345678",
    "123456789",
    "qwerty",
    "1234567890",
    "password123",
    "admin123",
    "iloveyou",
    "password1234",
}


def validate_password_complexity(password: str) -> str:
    """
    Validates a password against complexity rules:
    - Between 8 and 64 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one number
    - At least one special character
    - No spaces
    - Not in a list of common weak passwords
    """
    if password.lower() in COMMON_WEAK_PASSWORDS:
        raise ValueError("Password is too common and weak")

    if not (8 <= len(password) <= 64):
        raise ValueError("Password must be between 8 and 64 characters long")

    if " " in password:
        raise ValueError("Password must not contain spaces")

    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")

    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")

    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one number")

    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("Password must contain at least one special character")

    return password
