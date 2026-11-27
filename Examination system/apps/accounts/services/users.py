from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from ..models import AccountAuditLog, User


def create_user(
    *,
    username,
    password=None,
    role=User.Role.CANDIDATE,
    email="",
    first_name="",
    last_name="",
    department=None,
    degrees=(),
    subjects=(),
    is_active=True,
    is_staff=False,
    is_superuser=False,
    theme=User.Theme.IVORY,
    actor=None,
    validate=True,
):
    username = username.strip().lower()
    email = (email or "").strip().lower()
    if not username:
        raise ValidationError({"username": "Enter an identifier."})
    if role not in User.Role.values:
        raise ValidationError({"role": "Choose a valid user role."})
    if is_superuser and role != User.Role.ADMIN:
        raise ValidationError({"role": "Only administrators can be superusers."})

    user = User(
        username=username,
        email=email,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        role=role,
        department=department,
        is_active=is_active,
        is_staff=is_staff,
        is_superuser=is_superuser,
        theme=theme,
    )

    if password is None:
        user.set_unusable_password()
    else:
        if validate:
            validate_password(password, user=user)
        user.set_password(password)

    if User.objects.filter(username__iexact=username).exists():
        raise ValidationError({"username": "A user with this identifier already exists."})
    if email and User.objects.filter(email__iexact=email).exists():
        raise ValidationError({"email": "A user with this email already exists."})

    user.full_clean(exclude=("password", "last_login"), validate_unique=False)

    try:
        with transaction.atomic():
            user.save()
            if degrees:
                user.degrees.set(degrees)
            if subjects:
                user.subjects.set(subjects)
            AccountAuditLog.objects.create(
                actor=actor,
                target_user=user,
                action=AccountAuditLog.Action.USER_CREATED,
                details={"username": username, "role": role},
            )
    except IntegrityError as error:
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError(
                {"username": "A user with this identifier already exists."}
            ) from error
        if email and User.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                {"email": "A user with this email already exists."}
            ) from error
        raise

    return user
