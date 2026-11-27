from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from .catalog import Degree, Department, Subject


class UserManager(DjangoUserManager):
    def get_by_natural_key(self, username):
        return self.get(username__iexact=username.strip())

    def create_user(self, username, email=None, password=None, **extra_fields):
        from ..services.users import create_user

        return create_user(
            username=username,
            email=email or "",
            password=password,
            **extra_fields,
        )

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields["role"] = self.model.Role.ADMIN
        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        return self.create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrator"
        EXAMINER = "examiner", "Examiner"
        CANDIDATE = "candidate", "Candidate"

    class Theme(models.TextChoices):
        IVORY = "ivory", "Ivory"
        LAVENDER = "lavender", "Lavender"
        MAUVE = "mauve", "Mauve"
        ROSE = "rose", "Rose"
        SAGE = "sage", "Sage"
        PLUM = "plum", "Plum"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CANDIDATE,
    )
    theme = models.CharField(
        max_length=16,
        choices=Theme.choices,
        default=Theme.IVORY,
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="users",
        blank=True,
        null=True,
    )
    degrees = models.ManyToManyField(
        Degree,
        through="UserDegree",
        related_name="users",
        blank=True,
    )
    subjects = models.ManyToManyField(
        Subject,
        through="UserSubject",
        related_name="users",
        blank=True,
    )

    objects = UserManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=("admin", "examiner", "candidate")),
                name="accounts_user_valid_role",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    theme__in=("ivory", "lavender", "mauve", "rose", "sage", "plum")
                ),
                name="accounts_user_valid_theme",
            ),
            models.CheckConstraint(
                condition=Q(username=Lower("username")),
                name="accounts_user_username_lowercase",
            ),
            models.UniqueConstraint(
                Lower("username"),
                name="accounts_user_username_ci_uniq",
            ),
            models.UniqueConstraint(
                Lower("email"),
                condition=~Q(email=""),
                name="accounts_user_email_ci_uniq",
            ),
        ]

    def save(self, *args, **kwargs):
        self.username = self.username.strip().lower()
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username
