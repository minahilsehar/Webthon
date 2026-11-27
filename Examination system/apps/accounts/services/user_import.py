import csv
import io

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import Degree, Department, Subject, User
from .users import create_user


MAX_IMPORT_ROWS = 20
IMPORT_BATCH_SIZE = 10
REQUIRED_COLUMNS = {"username", "password", "role"}
OPTIONAL_COLUMNS = {
    "email",
    "first_name",
    "last_name",
    "department",
    "degrees",
    "subjects",
}


def import_users(actor, uploaded_file):
    if uploaded_file.size > 512 * 1024:
        raise ValidationError("The file exceeds 512 KB. No rows were imported.")

    try:
        content = uploaded_file.read().decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValidationError("The CSV must be UTF-8 encoded.") from error

    reader = csv.DictReader(io.StringIO(content), strict=True)
    columns = [
        (column or "").strip().lower()
        for column in (reader.fieldnames or ())
    ]
    if not columns:
        raise ValidationError("The CSV must include a header row.")
    if any(not column for column in columns):
        raise ValidationError("The CSV contains a blank column name.")
    if len(columns) != len(set(columns)):
        raise ValidationError("The CSV contains duplicate column names.")
    missing_columns = REQUIRED_COLUMNS - set(columns)
    if missing_columns:
        raise ValidationError(
            "The CSV is missing required columns: "
            + ", ".join(sorted(missing_columns))
            + "."
        )
    unexpected_columns = set(columns) - REQUIRED_COLUMNS - OPTIONAL_COLUMNS
    if unexpected_columns:
        raise ValidationError(
            "Unrecognized CSV columns: "
            + ", ".join(sorted(unexpected_columns))
            + "."
        )
    reader.fieldnames = columns

    rows = []
    try:
        for line_number, raw_row in enumerate(reader, start=2):
            if not any((value or "").strip() for value in raw_row.values()):
                continue
            rows.append((line_number, raw_row))
            if len(rows) > MAX_IMPORT_ROWS:
                raise ValidationError(
                    "This CSV has more than 20 user rows. No rows were imported; "
                    "split the file into smaller uploads. For larger imports, use a "
                    "background worker so processing does not block a web request."
                )
    except csv.Error as error:
        raise ValidationError(f"The CSV is malformed: {error}") from error
    if not rows:
        raise ValidationError("The CSV contains no user rows.")

    valid_rows = []
    errors = []
    seen_usernames = set()
    seen_emails = set()

    for line_number, raw_row in rows:
        row, row_errors = _validate_row(raw_row)
        if not row_errors and row["username"] in seen_usernames:
            row_errors.append(("skipped", "Identifier is duplicated in this file."))
        if (
            not row_errors
            and row["email"]
            and row["email"] in seen_emails
        ):
            row_errors.append(("skipped", "Email is duplicated in this file."))
        if not row_errors and User.objects.filter(
            username__iexact=row["username"]
        ).exists():
            row_errors.append(("skipped", "Identifier already exists."))
        if not row_errors and row["email"] and User.objects.filter(
            email__iexact=row["email"]
        ).exists():
            row_errors.append(("skipped", "Email already exists."))

        if row_errors:
            errors.extend(
                {"line": line_number, "kind": kind, "message": message}
                for kind, message in row_errors
            )
            continue

        seen_usernames.add(row["username"])
        if row["email"]:
            seen_emails.add(row["email"])
        valid_rows.append((line_number, row))

    created = 0
    for batch_start in range(0, len(valid_rows), IMPORT_BATCH_SIZE):
        batch = valid_rows[batch_start : batch_start + IMPORT_BATCH_SIZE]
        with transaction.atomic():
            for line_number, row in batch:
                try:
                    create_user(actor=actor, **row)
                except ValidationError as error:
                    messages = error.messages
                    kind = (
                        "skipped"
                        if any("already exists" in message.lower() for message in messages)
                        else "failed"
                    )
                    errors.extend(
                        {"line": line_number, "kind": kind, "message": message}
                        for message in messages
                    )
                else:
                    created += 1

    return {
        "total": len(rows),
        "created": created,
        "skipped": sum(error["kind"] == "skipped" for error in errors),
        "failed": sum(error["kind"] == "failed" for error in errors),
        "errors": errors,
    }


def _validate_row(raw_row):
    errors = []
    if None in raw_row:
        return {}, [("failed", "The row has more values than the header.")]

    values = {
        key: (raw_row.get(key) or "").strip()
        for key in REQUIRED_COLUMNS | OPTIONAL_COLUMNS
    }
    username = values["username"].lower()
    email = values["email"].lower()
    role = values["role"].lower()

    if not username:
        errors.append(("failed", "Identifier is required."))
    if role not in User.Role.values:
        errors.append(("failed", "Role must be admin, examiner, or candidate."))
    if not values["password"]:
        errors.append(("failed", "Password is required."))

    department = None
    if values["department"]:
        try:
            department = Department.objects.get(name__iexact=values["department"])
        except Department.DoesNotExist:
            errors.append(("failed", "Department does not exist."))

    degrees = _resolve_catalog_names(
        Degree,
        values["degrees"],
        "Degree",
        errors,
    )
    subjects = _resolve_catalog_names(
        Subject,
        values["subjects"],
        "Subject",
        errors,
    )

    user = User(
        username=username,
        email=email,
        first_name=values["first_name"],
        last_name=values["last_name"],
        role=role,
        department=department,
    )
    if username:
        try:
            user.full_clean(
                exclude=("password", "last_login"),
                validate_unique=False,
                validate_constraints=False,
            )
        except ValidationError as error:
            errors.extend(("failed", message) for message in error.messages)
    if values["password"]:
        try:
            validate_password(values["password"], user=user)
        except ValidationError as error:
            errors.extend(("failed", message) for message in error.messages)

    if errors:
        return {}, errors
    return {
        "username": username,
        "email": email,
        "password": values["password"],
        "role": role,
        "first_name": values["first_name"],
        "last_name": values["last_name"],
        "department": department,
        "degrees": degrees,
        "subjects": subjects,
    }, []


def _resolve_catalog_names(model, value, label, errors):
    names = list(dict.fromkeys(name.strip() for name in value.split(";") if name.strip()))
    items = []
    for name in names:
        try:
            items.append(model.objects.get(name__iexact=name))
        except model.DoesNotExist:
            errors.append(("failed", f"{label} '{name}' does not exist."))
    return items
