from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from accounts.models import User
from .models import (
    Attempt,
    AttemptQuestion,
    AuditLog,
    Enrollment,
    Exam,
    Question,
)
from .services import (
    AttemptLimitReached,
    AttemptStartDenied,
    start_attempt,
    update_exam_attempt_policy,
)


@pytest.fixture
def exam_setup(db):
    examiner = User.objects.create_user(username="examiner", role=User.Role.EXAMINER)
    candidate = User.objects.create_user(username="candidate")
    exam = Exam.objects.create(
        owner=examiner,
        title="Sample exam",
        duration_minutes=30,
        status=Exam.Status.PUBLISHED,
        max_attempts=3,
    )
    enrollment = Enrollment.objects.create(exam=exam, candidate=candidate)
    question = Question.objects.create(
        exam=exam,
        prompt="Choose one",
        options=["A", "B"],
        answer_key=["A"],
        position=1,
    )
    return examiner, candidate, exam, enrollment, question


@pytest.mark.django_db
def test_start_attempt_creates_snapshot_and_audit_entry(exam_setup):
    _examiner, candidate, exam, _enrollment, question = exam_setup

    attempt = start_attempt(candidate, exam)

    snapshot = AttemptQuestion.objects.get(attempt=attempt)
    assert attempt.attempt_number == 1
    assert attempt.status == Attempt.Status.IN_PROGRESS
    assert snapshot.question_id == question.pk
    assert snapshot.answer_key == question.answer_key
    assert AuditLog.objects.filter(
        exam=exam,
        action=AuditLog.Action.ATTEMPT_STARTED,
    ).count() == 1


@pytest.mark.django_db
def test_start_attempt_resumes_active_attempt_without_consuming_another(exam_setup):
    _examiner, candidate, exam, _enrollment, _question = exam_setup

    first = start_attempt(candidate, exam)
    resumed = start_attempt(candidate, exam)

    assert resumed.pk == first.pk
    assert Attempt.objects.filter(candidate=candidate, exam=exam).count() == 1


@pytest.mark.django_db
def test_start_attempt_refuses_when_limit_is_exhausted(exam_setup):
    _examiner, candidate, exam, _enrollment, _question = exam_setup
    exam.max_attempts = 1
    exam.save(update_fields=("max_attempts",))
    first = start_attempt(candidate, exam)
    first.status = Attempt.Status.ABANDONED
    first.save(update_fields=("status",))

    with pytest.raises(AttemptLimitReached, match="used all 1 attempts"):
        start_attempt(candidate, exam)


@pytest.mark.django_db
def test_attempts_three_and_fourth_start_is_refused(exam_setup):
    _examiner, candidate, exam, _enrollment, _question = exam_setup
    attempts = []
    for expected_number in range(1, 4):
        attempt = start_attempt(candidate, exam)
        assert attempt.attempt_number == expected_number
        attempt.status = Attempt.Status.SUBMITTED
        attempt.save(update_fields=("status",))
        attempts.append(attempt)

    with pytest.raises(AttemptLimitReached, match="used all 3 attempts"):
        start_attempt(candidate, exam)

    assert len(attempts) == 3


@pytest.mark.django_db
def test_expired_attempt_counts_toward_limit(exam_setup):
    _examiner, candidate, exam, _enrollment, _question = exam_setup
    expired = Attempt.objects.create(
        exam=exam,
        candidate=candidate,
        attempt_number=1,
        status=Attempt.Status.EXPIRED,
        deadline=timezone.now() - timedelta(minutes=1),
    )

    next_attempt = start_attempt(candidate, exam)

    assert expired.attempt_number == 1
    assert next_attempt.attempt_number == 2


@pytest.mark.django_db
def test_sandbox_attempt_does_not_consume_limit(exam_setup):
    _examiner, candidate, exam, _enrollment, _question = exam_setup
    exam.max_attempts = 1
    exam.save(update_fields=("max_attempts",))
    Attempt.objects.create(
        exam=exam,
        candidate=candidate,
        attempt_number=1,
        status=Attempt.Status.SUBMITTED,
        is_sandbox=True,
        deadline=timezone.now(),
    )

    attempt = start_attempt(candidate, exam)

    assert attempt.attempt_number == 2
    assert not attempt.is_sandbox


@pytest.mark.django_db
def test_start_attempt_requires_candidate_enrollment_and_available_exam(exam_setup):
    examiner, candidate, exam, enrollment, _question = exam_setup
    enrollment.is_active = False
    enrollment.save(update_fields=("is_active",))
    with pytest.raises(AttemptStartDenied, match="not enrolled"):
        start_attempt(candidate, exam)

    enrollment.is_active = True
    enrollment.save(update_fields=("is_active",))
    with pytest.raises(AttemptStartDenied, match="Only active candidates"):
        start_attempt(examiner, exam)

    exam.opens_at = timezone.now() + timedelta(minutes=1)
    exam.save(update_fields=("opens_at",))
    with pytest.raises(AttemptStartDenied, match="not open yet"):
        start_attempt(candidate, exam)


@pytest.mark.django_db
def test_exam_attempt_policy_rejects_limit_below_used_and_audits_changes(exam_setup):
    examiner, candidate, exam, _enrollment, _question = exam_setup
    attempt = Attempt.objects.create(
        exam=exam,
        candidate=candidate,
        attempt_number=2,
        status=Attempt.Status.SUBMITTED,
        deadline=timezone.now(),
    )

    with pytest.raises(ValidationError, match="cannot be lower than 2"):
        update_exam_attempt_policy(
            examiner,
            exam,
            max_attempts=1,
            scoring_policy=Exam.ScoringPolicy.HIGHEST,
        )

    updated = update_exam_attempt_policy(
        examiner,
        exam,
        max_attempts=4,
        scoring_policy=Exam.ScoringPolicy.LATEST,
    )
    audit = AuditLog.objects.get(action=AuditLog.Action.ATTEMPT_LIMIT_CHANGED)

    assert updated.max_attempts == 4
    assert updated.scoring_policy == Exam.ScoringPolicy.LATEST
    assert audit.details == {"old_max_attempts": 3, "new_max_attempts": 4}
    assert attempt.attempt_number == 2


@pytest.mark.django_db
def test_exam_attempt_policy_rejects_another_examiner(exam_setup):
    _examiner, _candidate, exam, _enrollment, _question = exam_setup
    other_examiner = User.objects.create_user(
        username="other",
        role=User.Role.EXAMINER,
    )

    with pytest.raises(PermissionDenied):
        update_exam_attempt_policy(
            other_examiner,
            exam,
            max_attempts=2,
            scoring_policy=Exam.ScoringPolicy.HIGHEST,
        )
