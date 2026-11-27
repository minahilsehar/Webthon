from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.db import models


class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields["role"] = self.model.Role.ADMIN
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrator"
        EXAMINER = "examiner", "Examiner"
        CANDIDATE = "candidate", "Candidate"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CANDIDATE,
    )

    objects = UserManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=("admin", "examiner", "candidate")),
                name="accounts_user_valid_role",
            ),
        ]

    def __str__(self):
        return self.username
