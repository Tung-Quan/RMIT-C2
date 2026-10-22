import pytest

from app.core.password_validation import validate_password_complexity


def test_valid_password():
    assert validate_password_complexity("StrongP@ssw0rd") == "StrongP@ssw0rd"


def test_too_short_password():
    with pytest.raises(ValueError, match="between 8 and 64 characters"):
        validate_password_complexity("Str0ng!")


def test_no_uppercase_password():
    with pytest.raises(ValueError, match="at least one uppercase letter"):
        validate_password_complexity("strongp@ssw0rd")


def test_no_lowercase_password():
    with pytest.raises(ValueError, match="at least one lowercase letter"):
        validate_password_complexity("STRONGP@SSW0RD")


def test_no_number_password():
    with pytest.raises(ValueError, match="at least one number"):
        validate_password_complexity("StrongP@ssword")


def test_no_special_char_password():
    with pytest.raises(ValueError, match="at least one special character"):
        validate_password_complexity("StrongPassw0rd")


def test_contains_space_password():
    with pytest.raises(ValueError, match="must not contain spaces"):
        validate_password_complexity("Strong P@ssw0rd")


def test_common_weak_password():
    with pytest.raises(ValueError, match="too common and weak"):
        validate_password_complexity("password")
