from django.conf import settings
from django.db import models


class UserPhoto(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="photo",
    )
    image = models.BinaryField(max_length=10 * 1024)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Photo for {self.user}"
