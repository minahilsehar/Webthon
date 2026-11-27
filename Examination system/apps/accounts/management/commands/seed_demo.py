import os

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Create local-only demo users for each account role."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo users can only be created when DEBUG=true.")

        password = os.environ.get("DEMO_PASSWORD")
        if not password:
            raise CommandError("Set DEMO_PASSWORD to a strong local-only password.")

        users = (
            ("demo-admin", "demo-admin@example.test", User.Role.ADMIN),
            ("demo-examiner", "demo-examiner@example.test", User.Role.EXAMINER),
            ("demo-candidate", "demo-candidate@example.test", User.Role.CANDIDATE),
        )
        for username, email, role in users:
            if User.objects.filter(username=username).exists():
                self.stdout.write(f"Kept existing account: {username}")
                continue

            user = User(username=username, email=email, role=role)
            validate_password(password, user)
            user.set_password(password)
            if role == User.Role.ADMIN:
                user.is_staff = True
                user.is_superuser = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created {role} account: {username}"))
