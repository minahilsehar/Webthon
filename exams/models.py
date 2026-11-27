from django.conf import settings
from django.db import models
from django.db.models import Q


class Exam(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    class ScoringPolicy(models.TextChoices):
        HIGHEST = "highest", "Highest"
        LATEST = "latest", "Latest"
        FIRST = "first", "First"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_exams",
    )
    title = models.CharField(max_length=200)
    duration_minutes = models.PositiveSmallIntegerField()
    opens_at = models.DateTimeField(blank=True, null=True)
    closes_at = models.DateTimeField(blank=True, null=True)
    max_attempts = models.PositiveSmallIntegerField(default=1)
    scoring_policy = models.CharField(
        max_length=10,
        choices=ScoringPolicy.choices,
        default=ScoringPolicy.HIGHEST,
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(max_attempts__gte=1) & Q(max_attempts__lte=10),
                name="exams_max_attempts_1_to_10",
            ),
            models.CheckConstraint(
                condition=Q(scoring_policy__in=("highest", "latest", "first")),
                name="exams_valid_scoring_policy",
            ),
            models.CheckConstraint(
                condition=Q(status__in=("draft", "published")),
                name="exams_valid_status",
            ),
        ]
        indexes = [
            models.Index(fields=("owner", "status"), name="exams_owner_status_idx"),
        ]

    def __str__(self):
        return self.title


class Question(models.Model):
    exam = models.ForeignKey(
        Exam,
        on_delete=models.PROTECT,
        related_name="questions",
    )
    prompt = models.TextField()
    options = models.JSONField(default=list)
    answer_key = models.JSONField(default=list)
    points = models.PositiveSmallIntegerField(default=1)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("position", "pk")
        indexes = [
            models.Index(fields=("exam", "is_active", "position"), name="exams_question_order_idx"),
        ]

    def __str__(self):
        return f"{self.exam}: question {self.position}"


class Enrollment(models.Model):
    exam = models.ForeignKey(
        Exam,
        on_delete=models.PROTECT,
        related_name="enrollments",
    )
    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="exam_enrollments",
    )
    is_active = models.BooleanField(default=True)
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("exam", "candidate"),
                name="exams_unique_enrollment",
            ),
        ]
        indexes = [
            models.Index(fields=("candidate", "is_active"), name="exams_candidate_active_idx"),
        ]

    def __str__(self):
        return f"{self.candidate} enrolled in {self.exam}"


class Attempt(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        SUBMITTED = "submitted", "Submitted"
        EXPIRED = "expired", "Expired"
        ABANDONED = "abandoned", "Abandoned"

    exam = models.ForeignKey(Exam, on_delete=models.PROTECT, related_name="attempts")
    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="exam_attempts",
    )
    attempt_number = models.PositiveIntegerField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
    )
    is_sandbox = models.BooleanField(default=False)
    started_at = models.DateTimeField(auto_now_add=True)
    deadline = models.DateTimeField()
    submitted_at = models.DateTimeField(blank=True, null=True)
    score = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(attempt_number__gte=1),
                name="exams_attempt_number_gte_1",
            ),
            models.CheckConstraint(
                condition=Q(status__in=("in_progress", "submitted", "expired", "abandoned")),
                name="exams_valid_attempt_status",
            ),
            models.UniqueConstraint(
                fields=("candidate", "exam", "attempt_number"),
                name="exams_unique_candidate_attempt_number",
            ),
            models.UniqueConstraint(
                fields=("candidate", "exam"),
                condition=Q(status="in_progress"),
                name="exams_one_active_attempt",
            ),
        ]
        indexes = [
            models.Index(
                fields=("exam", "candidate", "is_sandbox"),
                name="exams_attempt_count_idx",
            ),
            models.Index(
                fields=("candidate", "status"),
                name="exams_candidate_status_idx",
            ),
        ]

    def __str__(self):
        return f"{self.candidate}: {self.exam} attempt {self.attempt_number}"


class AttemptQuestion(models.Model):
    attempt = models.ForeignKey(
        Attempt,
        on_delete=models.PROTECT,
        related_name="question_snapshots",
    )
    question = models.ForeignKey(Question, on_delete=models.PROTECT)
    prompt = models.TextField()
    options = models.JSONField(default=list)
    answer_key = models.JSONField(default=list)
    points = models.PositiveSmallIntegerField()
    position = models.PositiveIntegerField()

    class Meta:
        ordering = ("position", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("attempt", "question"),
                name="exams_unique_attempt_question",
            ),
        ]


class Answer(models.Model):
    attempt = models.ForeignKey(
        Attempt,
        on_delete=models.PROTECT,
        related_name="answers",
    )
    question = models.ForeignKey(
        AttemptQuestion,
        on_delete=models.PROTECT,
        related_name="answers",
    )
    value = models.JSONField(default=list)
    sequence = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("attempt", "question"),
                name="exams_unique_attempt_answer",
            ),
        ]
        indexes = [
            models.Index(fields=("attempt", "updated_at"), name="exams_answer_attempt_idx"),
        ]


class AuditLog(models.Model):
    class Action(models.TextChoices):
        ATTEMPT_STARTED = "attempt_started", "Attempt started"
        ATTEMPT_LIMIT_CHANGED = "attempt_limit_changed", "Attempt limit changed"

    exam = models.ForeignKey(Exam, on_delete=models.PROTECT, related_name="audit_logs")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="exam_audit_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=("exam", "created_at"), name="exams_audit_exam_time_idx"),
        ]
