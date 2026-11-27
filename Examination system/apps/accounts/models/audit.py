from django.conf import settings
from django.db import models


class AccountAuditLog(models.Model):
    class Action(models.TextChoices):
        USER_CREATED = "user_created", "User created"
        CATALOG_CREATED = "catalog_created", "Catalog item created"
        CATALOG_UPDATED = "catalog_updated", "Catalog item updated"
        CATALOG_DELETED = "catalog_deleted", "Catalog item deleted"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="account_audit_actions",
        blank=True,
        null=True,
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="account_audit_records",
        blank=True,
        null=True,
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    resource_type = models.CharField(max_length=64, blank=True)
    resource_id = models.CharField(max_length=64, blank=True)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = [
            models.Index(
                fields=("target_user", "created_at"),
                name="accounts_audit_target_time_idx",
            ),
        ]
