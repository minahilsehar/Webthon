import os

from django.db import transaction
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Degree, Department, Subject, User
from apps.accounts.services import create_user
from apps.exams.models import Enrollment, Exam, Question


class Command(BaseCommand):
    help = "Create judging-only demo accounts and examination data."

    def handle(self, *args, **options):
        if os.environ.get("DEMO_MODE", "").lower() != "true":
            raise CommandError(
                "Set DEMO_MODE=true to create judging-only accounts with known passwords."
            )

        with transaction.atomic():
            department, _ = Department.objects.get_or_create(
                name__iexact="Computing",
                defaults={"name": "Computing"},
            )
            degree, _ = Degree.objects.get_or_create(
                name__iexact="BSc Computer Science",
                defaults={"name": "BSc Computer Science"},
            )
            subject, _ = Subject.objects.get_or_create(
                name__iexact="Web Technologies",
                defaults={"name": "Web Technologies", "code": "WEB101"},
            )

            administrator = self._get_or_create_user(
                "admin",
                "admin",
                User.Role.ADMIN,
                "Demo",
                "Administrator",
                department,
                degree,
                subject,
            )
            examiner = self._get_or_create_user(
                "examiner",
                "examiner",
                User.Role.EXAMINER,
                "Demo",
                "Examiner",
                department,
                degree,
                subject,
                actor=administrator,
            )

            candidates = []
            for number in range(1, 4):
                identifier = f"2026-DEMO-{number:03}"
                candidate = self._get_or_create_user(
                    identifier,
                    "candidate",
                    User.Role.CANDIDATE,
                    "Demo",
                    f"Candidate {number}",
                    department,
                    degree,
                    subject,
                    actor=administrator,
                )
                candidates.append(candidate)

            published_exam = self._get_or_create_exam(
                examiner,
                "Web Technologies Practice",
                Exam.Status.PUBLISHED,
            )
            draft_exam = self._get_or_create_exam(
                examiner,
                "Computer Science Foundations",
                Exam.Status.DRAFT,
            )
            for exam in (published_exam, draft_exam):
                Question.objects.get_or_create(
                    exam=exam,
                    position=1,
                    defaults={
                        "prompt": "Which language structures web page content?",
                        "options": ["HTML", "SQL", "Bash"],
                        "answer_key": ["HTML"],
                        "points": 1,
                        "is_active": True,
                    },
                )
            for candidate in candidates:
                Enrollment.objects.get_or_create(
                    exam=published_exam,
                    candidate=candidate,
                    defaults={"is_active": True},
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Demo data is ready. These known passwords are for judging only; "
                "change or disable these accounts after the event."
            )
        )

    def _get_or_create_user(
        self,
        username,
        password,
        role,
        first_name,
        last_name,
        department,
        degree,
        subject,
        actor=None,
    ):
        existing = User.objects.filter(username__iexact=username).first()
        if existing:
            return existing
        user = create_user(
            actor=actor,
            username=username,
            password=password,
            validate=False,
            role=role,
            first_name=first_name,
            last_name=last_name,
            email=f"{username.lower()}@example.test",
            department=department,
            degrees=(degree,),
            subjects=(subject,),
            is_staff=role == User.Role.ADMIN,
            is_superuser=role == User.Role.ADMIN,
        )
        self.stdout.write(f"Created demo account: {user.username}")
        return user

    @staticmethod
    def _get_or_create_exam(owner, title, status):
        exam, _ = Exam.objects.get_or_create(
            owner=owner,
            title=title,
            defaults={
                "duration_minutes": 30,
                "max_attempts": 1,
                "scoring_policy": Exam.ScoringPolicy.HIGHEST,
                "status": status,
            },
        )
        return exam
