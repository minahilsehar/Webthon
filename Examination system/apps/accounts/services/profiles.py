from django.core.exceptions import PermissionDenied
from django.db import transaction

from ..models import AccountAuditLog, User


@transaction.atomic
def update_profile_details(actor, user, *, section, values):
    if (
        not actor.is_authenticated
        or not actor.is_active
        or actor.role != User.Role.ADMIN
    ):
        raise PermissionDenied("Only administrators may manage profile details.")

    target = User.objects.select_for_update().get(pk=user.pk)
    if section == "name":
        old_values = {
            "first_name": target.first_name,
            "last_name": target.last_name,
        }
        target.first_name = values["first_name"].strip()
        target.last_name = values["last_name"].strip()
        target.save(update_fields=("first_name", "last_name"))
        new_values = {
            "first_name": target.first_name,
            "last_name": target.last_name,
        }
    elif section == "department":
        old_values = _catalog_values((target.department,) if target.department else ())
        target.department = values["department"]
        target.save(update_fields=("department",))
        new_values = _catalog_values((target.department,) if target.department else ())
    elif section in {"degrees", "subjects"}:
        relation = getattr(target, section)
        old_values = _catalog_values(relation.all())
        selected = values[section]
        relation.set(selected)
        new_values = _catalog_values(relation.all())
    else:
        raise ValueError(f"Unknown profile section: {section}")

    AccountAuditLog.objects.create(
        actor=actor,
        target_user=target,
        action=AccountAuditLog.Action.PROFILE_UPDATED,
        resource_type=section,
        resource_id=str(target.pk),
        details={"old": old_values, "new": new_values},
    )
    return target


def _catalog_values(items):
    return [{"id": item.pk, "name": item.name} for item in items]
