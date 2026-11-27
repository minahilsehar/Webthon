from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from .models import (
    Attempt,
    AttemptQuestion,
    AuditLog,
    Enrollment,
    Exam,
    Question,
)


class AttemptStartDenied(PermissionDenied):
    status_code = 403


class AttemptLimitReached(AttemptStartDenied):
    status_code = 409


def start_attempt(user, exam):
    if not user.is_authenticated or not user.is_active or user.role != user.Role.CANDIDATE:
        raise AttemptStartDenied("Only active candidates can start an exam.")

    with transaction.atomic():
        try:
            enrollment = Enrollment.objects.select_for_update().get(
                exam_id=exam.pk,
                candidate_id=user.pk,
                is_active=True,
            )
        except Enrollment.DoesNotExist as error:
            raise AttemptStartDenied("You are not enrolled in this exam.") from error

        exam = Exam.objects.get(pk=enrollment.exam_id)
        now = timezone.now()
        if exam.status != Exam.Status.PUBLISHED:
            raise AttemptStartDenied("This exam is not available.")
        if exam.opens_at and now < exam.opens_at:
            raise AttemptStartDenied("This exam is not open yet.")
        if exam.closes_at and now >= exam.closes_at:
            raise AttemptStartDenied("The exam availability window has ended.")

        active_attempt = Attempt.objects.filter(
            candidate=user,
            exam=exam,
            status=Attempt.Status.IN_PROGRESS,
        ).first()
        if active_attempt and active_attempt.deadline > now:
            return active_attempt
        if active_attempt:
            active_attempt.status = Attempt.Status.EXPIRED
            active_attempt.save(update_fields=("status",))

        attempts_used = Attempt.objects.filter(
            candidate=user,
            exam=exam,
            is_sandbox=False,
        ).count()
        if attempts_used >= exam.max_attempts:
            raise AttemptLimitReached(
                f"You have used all {exam.max_attempts} attempts for this exam."
            )

        questions = list(
            Question.objects.filter(exam=exam, is_active=True).only(
                "id",
                "prompt",
                "options",
                "answer_key",
                "points",
                "position",
            )
        )
        if not questions:
            raise AttemptStartDenied("This exam has no available questions.")

        last_attempt_number = (
            Attempt.objects.filter(candidate=user, exam=exam).aggregate(
                last_number=Max("attempt_number")
            )["last_number"]
            or 0
        )
        deadline = now + timedelta(minutes=exam.duration_minutes)
        if exam.closes_at:
            deadline = min(deadline, exam.closes_at)

        try:
            with transaction.atomic():
                attempt = Attempt.objects.create(
                    exam=exam,
                    candidate=user,
                    attempt_number=last_attempt_number + 1,
                    deadline=deadline,
                )
                AttemptQuestion.objects.bulk_create(
                    [
                        AttemptQuestion(
                            attempt=attempt,
                            question=question,
                            prompt=question.prompt,
                            options=question.options,
                            answer_key=question.answer_key,
                            points=question.points,
                            position=question.position,
                        )
                        for question in questions
                    ]
                )
                AuditLog.objects.create(
                    exam=exam,
                    actor=user,
                    action=AuditLog.Action.ATTEMPT_STARTED,
                    details={
                        "attempt_id": attempt.pk,
                        "attempt_number": attempt.attempt_number,
                    },
                )
        except IntegrityError:
            active_attempt = Attempt.objects.filter(
                candidate=user,
                exam=exam,
                status=Attempt.Status.IN_PROGRESS,
            ).first()
            if active_attempt:
                return active_attempt
            raise

        return attempt


@transaction.atomic
def update_exam_attempt_policy(actor, exam, *, max_attempts, scoring_policy):
    if (
        not actor.is_authenticated
        or not actor.is_active
        or actor.role != actor.Role.EXAMINER
        or exam.owner_id != actor.pk
    ):
        raise PermissionDenied("You may only update your own exam settings.")
    if not isinstance(max_attempts, int) or not 1 <= max_attempts <= 10:
        raise ValidationError("Attempts allowed must be between 1 and 10.")
    if scoring_policy not in Exam.ScoringPolicy.values:
        raise ValidationError("Choose a valid scoring policy.")

    list(
        Enrollment.objects.select_for_update()
        .filter(exam=exam)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    locked_exam = Exam.objects.select_for_update().get(pk=exam.pk)
    highest_used = (
        Attempt.objects.filter(
            exam=locked_exam,
            is_sandbox=False,
            candidate__exam_enrollments__exam=locked_exam,
        ).aggregate(highest=Max("attempt_number"))["highest"]
        or 0
    )
    if max_attempts < highest_used:
        raise ValidationError(
            f"Attempts allowed cannot be lower than {highest_used}, "
            "the highest number already used."
        )

    old_max_attempts = locked_exam.max_attempts
    locked_exam.max_attempts = max_attempts
    locked_exam.scoring_policy = scoring_policy
    locked_exam.save(update_fields=("max_attempts", "scoring_policy"))
    if old_max_attempts != max_attempts:
        AuditLog.objects.create(
            exam=locked_exam,
            actor=actor,
            action=AuditLog.Action.ATTEMPT_LIMIT_CHANGED,
            details={
                "old_max_attempts": old_max_attempts,
                "new_max_attempts": max_attempts,
            },
        )
    return locked_exam
