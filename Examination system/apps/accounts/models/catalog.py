from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower


class NamedCatalog(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        abstract = True
        ordering = ("name", "pk")
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="%(app_label)s_%(class)s_name_ci_uniq",
            ),
        ]

    def __str__(self):
        return self.name


class Department(NamedCatalog):
    class Meta(NamedCatalog.Meta):
        verbose_name_plural = "departments"


class Degree(NamedCatalog):
    pass


class Subject(NamedCatalog):
    code = models.CharField(max_length=32, blank=True)

    class Meta(NamedCatalog.Meta):
        constraints = NamedCatalog.Meta.constraints + [
            models.UniqueConstraint(
                Lower("code"),
                condition=~Q(code=""),
                name="accounts_subject_code_ci_uniq",
            ),
        ]


class UserDegree(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="degree_links",
    )
    degree = models.ForeignKey(
        Degree,
        on_delete=models.PROTECT,
        related_name="user_links",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "degree"),
                name="accounts_unique_user_degree",
            ),
        ]


class UserSubject(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="subject_links",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="user_links",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "subject"),
                name="accounts_unique_user_subject",
            ),
        ]
