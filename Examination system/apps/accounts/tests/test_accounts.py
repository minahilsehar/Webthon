import pytest
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.hashers import identify_hasher, make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import ProtectedError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory

from apps.exams.models import Enrollment
from apps.accounts.models import (
    AccountAuditLog,
    Degree,
    Department,
    Subject,
    User,
)
from apps.accounts.controllers.theme import save_theme
from apps.accounts.services import create_user
from apps.accounts.services.user_import import import_users


def test_user_roles_are_defined():
    assert {value for value, _label in User.Role.choices} == {
        "admin",
        "examiner",
        "candidate",
    }


def test_new_user_defaults_to_candidate():
    user = User(username="sample")
    assert user.role == User.Role.CANDIDATE
    assert user.theme == User.Theme.IVORY


def test_theme_choices_and_database_constraint():
    assert set(User.Theme.values) == {
        "ivory",
        "lavender",
        "mauve",
        "rose",
        "sage",
        "plum",
    }
    assert any(
        constraint.name == "accounts_user_valid_theme"
        for constraint in User._meta.constraints
    )


def test_theme_preference_is_saved_to_authenticated_user(monkeypatch):
    user = User(username="sample")
    saved_fields = []
    monkeypatch.setattr(
        user,
        "save",
        lambda *, update_fields: saved_fields.extend(update_fields),
    )
    request = RequestFactory().post("/accounts/theme/", {"theme": "plum"})
    request.user = user

    response = save_theme(request)

    assert response.status_code == 204
    assert user.theme == User.Theme.PLUM
    assert saved_fields == ["theme"]


def test_invalid_theme_preference_is_rejected():
    request = RequestFactory().post("/accounts/theme/", {"theme": "system"})
    request.user = User(username="sample")

    response = save_theme(request)

    assert response.status_code == 400


def test_theme_preference_requires_authentication():
    request = RequestFactory().post("/accounts/theme/", {"theme": "plum"})
    request.user = AnonymousUser()

    assert save_theme(request).status_code == 302


def test_theme_preference_post_requires_csrf_token():
    client = Client(enforce_csrf_checks=True)

    assert client.post("/accounts/theme/", {"theme": "plum"}).status_code == 403


def test_authentication_security_settings():
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert settings.SESSION_ENGINE == "django.contrib.sessions.backends.db"
    assert settings.SESSION_COOKIE_HTTPONLY
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"
    assert settings.CSRF_COOKIE_HTTPONLY
    assert settings.CSRF_COOKIE_SAMESITE == "Lax"


def test_database_uses_app_role_tls_setting_and_role_constraint():
    database = settings.DATABASES["default"]
    assert database["USER"].lower() != "postgres"
    assert database["OPTIONS"]["sslmode"] in {
        "disable",
        "allow",
        "prefer",
        "require",
        "verify-ca",
        "verify-full",
    }
    assert any(
        constraint.name == "accounts_user_valid_role"
        for constraint in User._meta.constraints
    )


def test_argon2_is_the_default_password_hasher():
    assert identify_hasher(make_password("test-password")).algorithm == "argon2"


def test_public_homepage_and_login_page_render():
    client = Client()

    home = client.get("/")
    login = client.get("/accounts/login/")

    assert home.status_code == 200
    assert b"Imtihanify" in home.content
    assert b"Examflow" not in home.content
    assert b'data-theme="ivory"' in home.content
    assert b'data-theme-key="anonymous"' in home.content
    assert b"/static/css/app.css" in home.content
    assert b'rel="manifest"' in home.content
    assert b"/static/manifest.json" in home.content
    assert home.content.count(b'name="theme"') == 6
    assert b'role="switch"' in home.content
    assert b"images/theme-day.png" in home.content
    assert b"images/theme-night.png" in home.content
    assert b"/static/js/theme-init.js" in home.content
    assert b"/static/js/vendor/htmx.min.js" in home.content
    assert b"/static/js/vendor/alpine.min.js" in home.content
    assert b'id="platform"' in home.content
    assert b'id="how-it-works"' in home.content
    assert b'class="mobile-bottom-nav"' in home.content
    assert login.status_code == 200
    assert b'id="login-title"' in login.content
    assert b'id="id_username"' in login.content
    assert b'id="id_password"' in login.content
    assert b'name="csrfmiddlewaretoken"' in login.content


def test_demo_seed_command_requires_explicit_demo_mode(monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)

    with pytest.raises(CommandError, match="DEMO_MODE=true"):
        call_command("seed_demo")


@pytest.mark.django_db
def test_create_user_normalizes_identifier_and_saves_related_data():
    department = Department.objects.create(name="Computing")
    degree = Degree.objects.create(name="Computer Science")
    subject = Subject.objects.create(name="Web Technologies", code="WEB101")

    user = create_user(
        username="  New-Candidate-01 ",
        password="a-Long-Unique-Passphrase-94!",
        role=User.Role.CANDIDATE,
        email="Candidate@Example.Test",
        first_name="New",
        last_name="Candidate",
        department=department,
        degrees=(degree,),
        subjects=(subject,),
    )

    assert user.username == "new-candidate-01"
    assert user.email == "candidate@example.test"
    assert user.check_password("a-Long-Unique-Passphrase-94!")
    assert authenticate(
        RequestFactory().post("/accounts/login/"),
        username="NEW-CANDIDATE-01",
        password="a-Long-Unique-Passphrase-94!",
    ) == user
    assert list(user.degrees.all()) == [degree]
    assert list(user.subjects.all()) == [subject]
    assert AccountAuditLog.objects.get(target_user=user).details == {
        "username": "new-candidate-01",
        "role": User.Role.CANDIDATE,
    }


@pytest.mark.django_db
def test_create_user_rejects_case_insensitive_duplicate_identifier():
    create_user(username="Candidate-1", password=None)

    with pytest.raises(ValidationError, match="identifier already exists"):
        create_user(username="candidate-1", password=None)


@pytest.mark.django_db
def test_create_user_rolls_back_if_audit_write_fails(monkeypatch):
    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit storage failed")

    monkeypatch.setattr(AccountAuditLog.objects, "create", fail_audit)

    with pytest.raises(RuntimeError, match="audit storage failed"):
        create_user(username="rolled-back", password=None)

    assert not User.objects.filter(username="rolled-back").exists()


@pytest.mark.django_db
def test_assigned_catalog_items_cannot_be_deleted():
    degree = Degree.objects.create(name="Computer Science")
    user = create_user(username="candidate-2", degrees=(degree,))

    with pytest.raises(ProtectedError):
        degree.delete()

    assert user.degrees.filter(pk=degree.pk).exists()


@pytest.mark.django_db
def test_admin_user_creation_uses_atomic_service(client):
    administrator = create_user(
        username="account-admin",
        password="a-Unique-Admin-Passphrase-94!",
        role=User.Role.ADMIN,
        is_staff=True,
        is_superuser=True,
    )
    client.force_login(administrator)

    response = client.post(
        "/admin/accounts/user/add/",
        {
            "username": "created-in-admin",
            "email": "created@example.test",
            "first_name": "Created",
            "last_name": "Candidate",
            "role": User.Role.CANDIDATE,
            "password1": "a-Unique-Candidate-Passphrase-94!",
            "password2": "a-Unique-Candidate-Passphrase-94!",
            "_save": "Save",
        },
    )

    assert response.status_code == 302
    created = User.objects.get(username="created-in-admin")
    assert created.check_password("a-Unique-Candidate-Passphrase-94!")
    assert AccountAuditLog.objects.get(target_user=created).actor == administrator


@pytest.mark.django_db
def test_bulk_import_validates_all_rows_then_saves_valid_rows_in_batches():
    department = Department.objects.create(name="Computing")
    degree = Degree.objects.create(name="Computer Science")
    subject = Subject.objects.create(name="Web Technologies")
    administrator = create_user(username="import-admin", role=User.Role.ADMIN)
    csv_content = (
        "username,password,role,email,first_name,last_name,department,degrees,subjects\n"
        "2026-bulk-001,a-Unique-Bulk-Passphrase-94!,candidate,"
        "bulk1@example.test,Ada,Student,Computing,Computer Science,Web Technologies\n"
        "2026-bulk-002,short,candidate,bulk2@example.test,Sam,Student,"
        "Computing,Computer Science,Web Technologies\n"
    )

    result = import_users(
        administrator,
        SimpleUploadedFile("candidates.csv", csv_content.encode("utf-8")),
    )

    assert result["total"] == 2
    assert result["created"] == 1
    assert result["skipped"] == 0
    assert result["failed"] == 1
    assert result["errors"][0]["line"] == 3
    imported = User.objects.get(username="2026-bulk-001")
    assert imported.department == department
    assert list(imported.degrees.all()) == [degree]
    assert list(imported.subjects.all()) == [subject]
    assert "password" not in str(AccountAuditLog.objects.get(target_user=imported).details)

    repeated = import_users(
        administrator,
        SimpleUploadedFile("candidates.csv", csv_content.encode("utf-8")),
    )
    assert repeated["created"] == 0
    assert repeated["skipped"] == 1
    assert User.objects.filter(username="2026-bulk-001").count() == 1


@pytest.mark.django_db
def test_bulk_import_admin_page_uses_account_creation_service(client):
    administrator = create_user(
        username="import-page-admin",
        role=User.Role.ADMIN,
        is_staff=True,
        is_superuser=True,
    )
    client.force_login(administrator)
    csv_content = (
        "username,password,role\n"
        "2026-page-001,a-Unique-Page-Passphrase-94!,candidate\n"
    )

    response = client.post(
        "/admin/accounts/user/import/",
        {
            "csv_file": SimpleUploadedFile(
                "users.csv",
                csv_content.encode("utf-8"),
            )
        },
    )

    assert response.status_code == 200
    assert User.objects.filter(username="2026-page-001").exists()
    assert b"Created: 1" in response.content


@pytest.mark.django_db
def test_bulk_import_rejects_more_than_twenty_rows_without_saving():
    rows = ["username,password,role"] + [
        f"2026-limit-{number},a-Unique-Import-Passphrase-94!,candidate"
        for number in range(21)
    ]

    with pytest.raises(ValidationError, match="more than 20 user rows"):
        import_users(
            None,
            SimpleUploadedFile("users.csv", "\n".join(rows).encode("utf-8")),
        )

    assert User.objects.count() == 0


@pytest.mark.django_db
def test_demo_seed_is_idempotent_and_requires_demo_mode(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")

    call_command("seed_demo")
    call_command("seed_demo")

    assert User.objects.filter(username__in=("admin", "examiner")).count() == 2
    assert User.objects.filter(username__startswith="2026-demo-").count() == 3
    assert User.objects.get(username="admin").check_password("admin")
    assert Enrollment.objects.count() == 3
