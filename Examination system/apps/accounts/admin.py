from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseForbidden
from django.template.response import TemplateResponse
from django.urls import path

from .forms import UserImportForm
from .models import AccountAuditLog, Degree, Department, Subject, User
from .services import create_user
from .services.user_import import import_users


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    change_list_template = "admin/accounts/user/change_list.html"
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Role", {"fields": ("role",)}),
        ("Preferences", {"fields": ("theme",)}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        (
            "Account details",
            {"fields": ("first_name", "last_name", "email", "role")},
        ),
    )
    list_display = ("username", "email", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")

    def has_module_permission(self, request):
        return request.user.is_active and request.user.role == User.Role.ADMIN

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        custom_urls = [
            path(
                "import/",
                self.admin_site.admin_view(self.import_view),
                name="accounts_user_import",
            ),
        ]
        return custom_urls + super().get_urls()

    def import_view(self, request):
        if not self.has_add_permission(request):
            return HttpResponseForbidden()

        form = UserImportForm(request.POST or None, request.FILES or None)
        result = None
        if request.method == "POST" and form.is_valid():
            try:
                result = import_users(
                    request.user,
                    form.cleaned_data["csv_file"],
                )
            except ValidationError as error:
                form.add_error("csv_file", error)

        context = {
            **self.admin_site.each_context(request),
            "form": form,
            "opts": self.model._meta,
            "title": "Import users from CSV",
            "result": result,
        }
        return TemplateResponse(
            request,
            "admin/accounts/user/import.html",
            context,
        )

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return

        created = create_user(
            actor=request.user,
            username=form.cleaned_data["username"],
            email=form.cleaned_data.get("email", ""),
            first_name=form.cleaned_data.get("first_name", ""),
            last_name=form.cleaned_data.get("last_name", ""),
            password=form.cleaned_data.get("password1"),
            role=obj.role,
            is_staff=obj.role == User.Role.ADMIN,
            is_superuser=obj.role == User.Role.ADMIN,
        )
        obj.pk = created.pk
        obj.password = created.password


@admin.register(Department, Degree, Subject)
class CatalogAdmin(admin.ModelAdmin):
    ordering = ("name",)

    def get_list_display(self, request):
        if self.model is Subject:
            return ("name", "code")
        return ("name",)

    def get_search_fields(self, request):
        if self.model is Subject:
            return ("name", "code")
        return ("name",)

    def save_model(self, request, obj, form, change):
        previous = None
        if change:
            previous = self.model.objects.get(pk=obj.pk)
        super().save_model(request, obj, form, change)

        old_values = self._values(previous)
        new_values = self._values(obj)
        AccountAuditLog.objects.create(
            actor=request.user,
            action=(
                AccountAuditLog.Action.CATALOG_UPDATED
                if change
                else AccountAuditLog.Action.CATALOG_CREATED
            ),
            resource_type=self.model.__name__.lower(),
            resource_id=str(obj.pk),
            details={"old": old_values, "new": new_values},
        )

    def delete_model(self, request, obj):
        self._audit_deletion(request, obj)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            for obj in queryset:
                self._audit_deletion(request, obj)
            super().delete_queryset(request, queryset)

    def _audit_deletion(self, request, obj):
        AccountAuditLog.objects.create(
            actor=request.user,
            action=AccountAuditLog.Action.CATALOG_DELETED,
            resource_type=self.model.__name__.lower(),
            resource_id=str(obj.pk),
            details={"old": self._values(obj)},
        )

    @staticmethod
    def _values(obj):
        if obj is None:
            return None
        values = {"name": obj.name}
        if isinstance(obj, Subject):
            values["code"] = obj.code
        return values


@admin.register(AccountAuditLog)
class AccountAuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "actor", "target_user", "resource_type", "created_at")
    list_filter = ("action", "resource_type")
    readonly_fields = (
        "actor",
        "target_user",
        "action",
        "resource_type",
        "resource_id",
        "details",
        "created_at",
    )

    def has_module_permission(self, request):
        return request.user.is_active and request.user.role == User.Role.ADMIN

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
