from django.conf import settings
from django.contrib.auth.hashers import identify_hasher, make_password

from .models import User


def test_user_roles_are_defined():
    assert {value for value, _label in User.Role.choices} == {
        "admin",
        "examiner",
        "candidate",
    }


def test_new_user_defaults_to_candidate():
    assert User(username="sample").role == User.Role.CANDIDATE


def test_authentication_security_settings():
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert settings.SESSION_ENGINE == "django.contrib.sessions.backends.db"
    assert settings.SESSION_COOKIE_HTTPONLY
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"
    assert settings.CSRF_COOKIE_HTTPONLY
    assert settings.CSRF_COOKIE_SAMESITE == "Lax"


def test_argon2_is_the_default_password_hasher():
    assert identify_hasher(make_password("test-password")).algorithm == "argon2"
