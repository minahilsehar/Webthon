from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from .models import (
    Attempt,
    AttemptQuestion,
    Answer,
    AuditLog,
    Enrollment,
    Exam,
    Question,
)


class AttemptStartDenied(PermissionDenied):
    status_code = 403


class AttemptLimitReached(AttemptStartDenied):
    status_code = 409


class AttemptNotFound(PermissionDenied):
    status_code = 404


class AttemptClosed(PermissionDenied):
    status_code = 409


class AttemptSequenceConflict(AttemptClosed):
    def __init__(self, current_sequence):
        self.current_sequence = current_sequence
        super().__init__("This answer sequence was already used.")


def _score_attempt(attempt):
    answers = dict(attempt.answers.values_list("question_id", "value"))
    return sum(
        question.points
        for question in attempt.question_snapshots.all()
        if answers.get(question.pk) == question.answer_key
    )


def _expire_attempt(attempt, now):
    attempt.status = Attempt.Status.EXPIRED
    attempt.submitted_at = now
    attempt.score = _score_attempt(attempt)
    attempt.save(update_fields=("status", "submitted_at", "score"))


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

        deadline = now + timedelta(minutes=exam.duration_minutes)
        if exam.closes_at:
            deadline = min(deadline, exam.closes_at)

        try:
            with transaction.atomic():
                if active_attempt:
                    _expire_attempt(active_attempt, now)
                attempt = Attempt.objects.create(
                    exam=exam,
                    candidate=user,
                    attempt_number=attempts_used + 1,
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


def save_attempt_answer(user, attempt_id, question_id, sequence, value):
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ValidationError("Answer sequence must be a positive integer.")

    expired = False
    result = None
    with transaction.atomic():
        try:
            attempt = Attempt.objects.select_for_update().get(
                pk=attempt_id,
                candidate=user,
            )
        except Attempt.DoesNotExist as error:
            raise AttemptNotFound("Attempt not found.") from error

        now = timezone.now()
        if attempt.status != Attempt.Status.IN_PROGRESS:
            raise AttemptClosed("This attempt is no longer accepting answers.")
        if now >= attempt.deadline:
            _expire_attempt(attempt, now)
            expired = True
        else:
            try:
                question = AttemptQuestion.objects.get(pk=question_id, attempt=attempt)
            except AttemptQuestion.DoesNotExist as error:
                raise AttemptNotFound("Question not found for this attempt.") from error

            if not isinstance(value, list) or any(
                not isinstance(option, str) or option not in question.options
                for option in value
            ):
                raise ValidationError("Answer must contain only available options.")
            answer = Answer.objects.filter(attempt=attempt, question=question).first()
            if answer and sequence < answer.sequence:
                result = {"sequence": answer.sequence, "saved": True}
            elif answer and sequence == answer.sequence and value == answer.value:
                result = {"sequence": answer.sequence, "saved": True}
            elif answer and sequence == answer.sequence:
                raise AttemptSequenceConflict(answer.sequence)
            elif answer:
                answer.value = value
                answer.sequence = sequence
                answer.save(update_fields=("value", "sequence", "updated_at"))
                result = {"sequence": sequence, "saved": True}
            else:
                Answer.objects.create(
                    attempt=attempt,
                    question=question,
                    value=value,
                    sequence=sequence,
                )
                result = {"sequence": sequence, "saved": True}

    if expired:
        raise AttemptClosed("The exam time has ended.")
    return result


@transaction.atomic
def finish_attempt(user, attempt_id):
    try:
        attempt = Attempt.objects.select_for_update().get(
            pk=attempt_id,
            candidate=user,
        )
    except Attempt.DoesNotExist as error:
        raise AttemptNotFound("Attempt not found.") from error

    now = timezone.now()
    if attempt.status == Attempt.Status.IN_PROGRESS and now >= attempt.deadline:
        _expire_attempt(attempt, now)
    elif attempt.status == Attempt.Status.IN_PROGRESS:
        attempt.status = Attempt.Status.SUBMITTED
        attempt.submitted_at = now
        attempt.score = _score_attempt(attempt)
        attempt.save(update_fields=("status", "submitted_at", "score"))
    return attempt


@transaction.atomic
def heartbeat_attempt(user, attempt_id):
    try:
        attempt = Attempt.objects.select_for_update().get(
            pk=attempt_id,
            candidate=user,
        )
    except Attempt.DoesNotExist as error:
        raise AttemptNotFound("Attempt not found.") from error

    now = timezone.now()
    if attempt.status == Attempt.Status.IN_PROGRESS and now >= attempt.deadline:
        _expire_attempt(attempt, now)
    remaining = max(0, int((attempt.deadline - now).total_seconds()))
    return attempt, remaining


def official_attempt(candidate, exam):
    attempts = Attempt.objects.filter(
        candidate=candidate,
        exam=exam,
        is_sandbox=False,
        score__isnull=False,
        status__in=(Attempt.Status.SUBMITTED, Attempt.Status.EXPIRED),
    )
    if exam.scoring_policy == Exam.ScoringPolicy.HIGHEST:
        return attempts.order_by("-score", "attempt_number").first()
    if exam.scoring_policy == Exam.ScoringPolicy.LATEST:
        return attempts.order_by("-submitted_at", "-pk").first()
    return attempts.order_by("attempt_number").first()


@transaction.atomic
def publish_exam_results(actor, exam):
    if (
        not actor.is_authenticated
        or not actor.is_active
        or actor.role != actor.Role.EXAMINER
        or exam.owner_id != actor.pk
    ):
        raise PermissionDenied("You may only publish results for your own exam.")

    locked_exam = Exam.objects.select_for_update().get(pk=exam.pk)
    if not locked_exam.results_published:
        locked_exam.results_published = True
        locked_exam.save(update_fields=("results_published",))
        AuditLog.objects.create(
            exam=locked_exam,
            actor=actor,
            action=AuditLog.Action.RESULTS_PUBLISHED,
        )
    return locked_exam


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
