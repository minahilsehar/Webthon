import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from .models import (
    Attempt,
    AttemptQuestion,
    AuditLog,
    Enrollment,
    Exam,
    Question,
)
from .services import (
    AttemptClosed,
    AttemptLimitReached,
    AttemptNotFound,
    AttemptSequenceConflict,
    AttemptStartDenied,
    finish_attempt,
    heartbeat_attempt,
    official_attempt,
    publish_exam_results,
    save_attempt_answer,
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
        attempt_number=3,
        status=Attempt.Status.SUBMITTED,
        is_sandbox=True,
        deadline=timezone.now(),
    )

    attempt = start_attempt(candidate, exam)

    assert attempt.attempt_number == 1
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
    exam.opens_at = None
    exam.closes_at = timezone.now() - timedelta(minutes=1)
    exam.save(update_fields=("opens_at", "closes_at"))
    with pytest.raises(AttemptStartDenied, match="window has ended"):
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


@pytest.mark.django_db
def test_answer_autosave_is_idempotent_and_rejects_stale_or_conflicting_sequence(exam_setup):
    _examiner, candidate, exam, _enrollment, _question = exam_setup
    attempt = start_attempt(candidate, exam)
    question = attempt.question_snapshots.get()

    assert save_attempt_answer(candidate, attempt.pk, question.pk, 1, ["A"]) == {
        "sequence": 1,
        "saved": True,
    }
    assert save_attempt_answer(candidate, attempt.pk, question.pk, 1, ["A"]) == {
        "sequence": 1,
        "saved": True,
    }
    with pytest.raises(AttemptSequenceConflict) as conflict:
        save_attempt_answer(candidate, attempt.pk, question.pk, 1, ["B"])
    assert conflict.value.current_sequence == 1

    save_attempt_answer(candidate, attempt.pk, question.pk, 2, ["B"])
    stale = save_attempt_answer(candidate, attempt.pk, question.pk, 1, ["A"])
    answer = attempt.answers.get()

    assert stale == {"sequence": 2, "saved": True}
    assert answer.value == ["B"]
    assert answer.sequence == 2


@pytest.mark.django_db
def test_submit_scores_answers_once_and_is_idempotent(exam_setup):
    _examiner, candidate, _exam, _enrollment, _question = exam_setup
    attempt = start_attempt(candidate, _exam)
    question = attempt.question_snapshots.get()
    save_attempt_answer(candidate, attempt.pk, question.pk, 1, ["A"])

    submitted = finish_attempt(candidate, attempt.pk)
    repeated = finish_attempt(candidate, attempt.pk)

    assert submitted.status == Attempt.Status.SUBMITTED
    assert submitted.score == 1
    assert submitted.pk == repeated.pk
    assert Attempt.objects.filter(candidate=candidate, exam=_exam).count() == 1


@pytest.mark.django_db
def test_heartbeat_expires_attempt_and_answer_endpoint_refuses_it(exam_setup):
    _examiner, candidate, exam, _enrollment, _question = exam_setup
    attempt = start_attempt(candidate, exam)
    attempt.deadline = timezone.now() - timedelta(seconds=1)
    attempt.save(update_fields=("deadline",))

    expired, remaining = heartbeat_attempt(candidate, attempt.pk)

    assert expired.status == Attempt.Status.EXPIRED
    assert remaining == 0
    with pytest.raises(AttemptClosed):
        save_attempt_answer(
            candidate,
            attempt.pk,
            attempt.question_snapshots.get().pk,
            1,
            ["A"],
        )


@pytest.mark.django_db
def test_attempt_operations_hide_other_candidates_attempts(exam_setup):
    _examiner, candidate, exam, _enrollment, _question = exam_setup
    other_candidate = User.objects.create_user(username="other-candidate")
    attempt = start_attempt(candidate, exam)

    with pytest.raises(AttemptNotFound):
        heartbeat_attempt(other_candidate, attempt.pk)
    with pytest.raises(AttemptNotFound):
        finish_attempt(other_candidate, attempt.pk)


@pytest.mark.django_db
def test_official_attempt_follows_each_scoring_policy(exam_setup):
    _examiner, candidate, exam, _enrollment, _question = exam_setup
    now = timezone.now()
    first = Attempt.objects.create(
        exam=exam,
        candidate=candidate,
        attempt_number=1,
        status=Attempt.Status.SUBMITTED,
        deadline=now,
        submitted_at=now - timedelta(minutes=2),
        score=4,
    )
    second = Attempt.objects.create(
        exam=exam,
        candidate=candidate,
        attempt_number=2,
        status=Attempt.Status.SUBMITTED,
        deadline=now,
        submitted_at=now - timedelta(minutes=1),
        score=8,
    )
    third = Attempt.objects.create(
        exam=exam,
        candidate=candidate,
        attempt_number=3,
        status=Attempt.Status.SUBMITTED,
        deadline=now,
        submitted_at=now,
        score=6,
    )
    Attempt.objects.create(
        exam=exam,
        candidate=candidate,
        attempt_number=11,
        status=Attempt.Status.SUBMITTED,
        is_sandbox=True,
        deadline=now,
        submitted_at=now,
        score=100,
    )

    for policy, expected in (
        (Exam.ScoringPolicy.HIGHEST, second),
        (Exam.ScoringPolicy.LATEST, third),
        (Exam.ScoringPolicy.FIRST, first),
    ):
        exam.scoring_policy = policy
        assert official_attempt(candidate, exam).pk == expected.pk


@pytest.mark.django_db
def test_results_are_only_published_by_exam_owner(exam_setup):
    examiner, _candidate, exam, _enrollment, _question = exam_setup
    other_examiner = User.objects.create_user(
        username="other-owner",
        role=User.Role.EXAMINER,
    )

    with pytest.raises(PermissionDenied):
        publish_exam_results(other_examiner, exam)

    published = publish_exam_results(examiner, exam)

    assert published.results_published
    assert AuditLog.objects.filter(
        exam=exam,
        action=AuditLog.Action.RESULTS_PUBLISHED,
    ).count() == 1


@pytest.mark.django_db
def test_candidate_start_resume_and_attempt_page_hide_answer_keys(exam_setup):
    _examiner, candidate, exam, _enrollment, question = exam_setup
    question.answer_key = ["A"]
    question.save(update_fields=("answer_key",))
    client = Client()
    client.force_login(candidate)

    dashboard = client.get(reverse("candidate_dashboard"))
    instructions = client.get(reverse("instructions", args=(exam.pk,)))
    started = client.post(reverse("attempt_start", args=(exam.pk,)))
    attempt = Attempt.objects.get(candidate=candidate, exam=exam)
    page = client.get(reverse("attempt_detail", args=(attempt.pk,)))

    assert dashboard.status_code == 200
    assert b"Attempt 1 of 3" in dashboard.content
    assert instructions.status_code == 200
    assert b"3 attempts remaining" in instructions.content
    assert started.status_code == 302
    assert page.status_code == 200
    assert set(page.context["questions"][0]) == {"id", "prompt", "options", "answer"}
    assert "answer_key" not in page.context["questions"][0]
    assert client.post(reverse("attempt_start", args=(exam.pk,))).url == reverse(
        "attempt_detail", args=(attempt.pk,)
    )


@pytest.mark.django_db
def test_candidate_dashboard_shows_attempt_two_and_disables_exhausted_start(exam_setup):
    _examiner, candidate, exam, _enrollment, _question = exam_setup
    first = start_attempt(candidate, exam)
    first.status = Attempt.Status.SUBMITTED
    first.save(update_fields=("status",))
    second = start_attempt(candidate, exam)
    client = Client()
    client.force_login(candidate)

    dashboard = client.get(reverse("candidate_dashboard"))

    assert second.attempt_number == 2
    assert b"Attempt 2 of 3" in dashboard.content
    assert b"1 remaining" in dashboard.content

    second.status = Attempt.Status.SUBMITTED
    second.save(update_fields=("status",))
    third = start_attempt(candidate, exam)
    third.status = Attempt.Status.SUBMITTED
    third.save(update_fields=("status",))
    exam.max_attempts = 3
    exam.save(update_fields=("max_attempts",))
    dashboard = client.get(reverse("candidate_dashboard"))
    refused = client.post(reverse("attempt_start", args=(exam.pk,)))

    assert b"No attempts left" in dashboard.content
    assert b'aria-disabled="true"' in dashboard.content
    assert b"aria-describedby=" in dashboard.content
    assert refused.status_code == 409
    assert b"used all 3 attempts" in refused.content


@pytest.mark.django_db
def test_autosave_endpoint_checks_attempt_owner_and_request_shape(exam_setup):
    _examiner, candidate, exam, _enrollment, _question = exam_setup
    other_candidate = User.objects.create_user(username="other-client")
    attempt = start_attempt(candidate, exam)
    question = attempt.question_snapshots.get()
    client = Client()
    client.force_login(candidate)
    endpoint = reverse("answer_autosave", args=(attempt.pk,))

    invalid = client.post(endpoint, data="{", content_type="application/json")
    missing = client.post(
        endpoint,
        data='{"question_id": 1, "sequence": 1}',
        content_type="application/json",
    )
    saved = client.post(
        endpoint,
        data=json.dumps(
            {"question_id": question.pk, "sequence": 1, "value": ["A"]}
        ),
        content_type="application/json",
    )
    conflict = client.post(
        endpoint,
        data=json.dumps(
            {"question_id": question.pk, "sequence": 1, "value": ["B"]}
        ),
        content_type="application/json",
    )
    client.force_login(other_candidate)
    forbidden = client.post(
        endpoint,
        data=json.dumps(
            {"question_id": question.pk, "sequence": 2, "value": ["B"]}
        ),
        content_type="application/json",
    )

    assert invalid.status_code == 400
    assert missing.status_code == 400
    assert saved.status_code == 200
    assert saved.json() == {"sequence": 1, "saved": True}
    assert conflict.status_code == 409
    assert conflict.json()["sequence"] == 1
    assert forbidden.status_code == 404


@pytest.mark.django_db
def test_examiner_can_create_exam_question_enrollment_and_publish(exam_setup):
    examiner, candidate, _exam, _enrollment, _question = exam_setup
    client = Client()
    client.force_login(examiner)
    create = client.post(
        reverse("exam_create"),
        {
            "title": "New exam",
            "duration_minutes": 20,
            "max_attempts": 2,
            "scoring_policy": Exam.ScoringPolicy.LATEST,
            "status": Exam.Status.DRAFT,
        },
    )
    exam = Exam.objects.get(title="New exam")
    add_question = client.post(
        reverse("question_add", args=(exam.pk,)),
        {
            "prompt": "Choose A",
            "options": '["A", "B"]',
            "answer_key": '["A"]',
            "points": 1,
            "position": 1,
        },
    )
    update = client.post(
        reverse("exam_manage", args=(exam.pk,)),
        {
            "title": "New exam",
            "duration_minutes": 20,
            "max_attempts": 2,
            "scoring_policy": Exam.ScoringPolicy.LATEST,
            "status": Exam.Status.PUBLISHED,
        },
    )
    enroll = client.post(
        reverse("candidate_enroll", args=(exam.pk,)),
        {"candidate_username": candidate.username},
    )

    assert create.status_code == 302
    assert add_question.status_code == 302
    assert update.status_code == 302
    assert enroll.status_code == 302
    exam.refresh_from_db()
    assert exam.questions.count() == 1
    assert exam.status == Exam.Status.PUBLISHED
    assert Enrollment.objects.filter(exam=exam, candidate=candidate).exists()


@pytest.mark.django_db
def test_examiner_cannot_lower_limit_below_used_count_in_settings(exam_setup):
    examiner, candidate, exam, _enrollment, _question = exam_setup
    Attempt.objects.create(
        exam=exam,
        candidate=candidate,
        attempt_number=2,
        status=Attempt.Status.SUBMITTED,
        deadline=timezone.now(),
    )
    client = Client()
    client.force_login(examiner)

    response = client.post(
        reverse("exam_manage", args=(exam.pk,)),
        {
            "title": exam.title,
            "duration_minutes": exam.duration_minutes,
            "max_attempts": 1,
            "scoring_policy": exam.scoring_policy,
            "status": exam.status,
        },
    )

    assert response.status_code == 200
    assert b"cannot be lower than 2" in response.content
    exam.refresh_from_db()
    assert exam.max_attempts == 3


@pytest.mark.django_db
def test_candidate_cannot_open_another_candidates_attempt(exam_setup):
    _examiner, candidate, exam, _enrollment, _question = exam_setup
    other_candidate = User.objects.create_user(username="unauthorized")
    attempt = start_attempt(candidate, exam)
    client = Client()
    client.force_login(other_candidate)

    response = client.get(reverse("attempt_detail", args=(attempt.pk,)))

    assert response.status_code == 404


@pytest.mark.django_db
def test_candidate_sees_scores_only_after_publication(exam_setup):
    examiner, candidate, exam, _enrollment, _question = exam_setup
    attempt = Attempt.objects.create(
        exam=exam,
        candidate=candidate,
        attempt_number=1,
        status=Attempt.Status.SUBMITTED,
        deadline=timezone.now(),
        submitted_at=timezone.now(),
        score=0,
    )
    client = Client()
    client.force_login(candidate)
    history_url = reverse("attempt_history", args=(exam.pk,))

    hidden = client.get(history_url)
    publish_exam_results(examiner, exam)
    published = client.get(history_url)

    assert hidden.status_code == 200
    assert b"Not published" in hidden.content
    assert b"Counts as result" not in hidden.content
    assert published.status_code == 200
    assert b"0.00" in published.content
    assert b"Counts as result" in published.content


@pytest.mark.django_db
def test_examiner_monitoring_and_results_pages_render(exam_setup):
    examiner, candidate, exam, _enrollment, _question = exam_setup
    attempt = Attempt.objects.create(
        exam=exam,
        candidate=candidate,
        attempt_number=1,
        status=Attempt.Status.SUBMITTED,
        deadline=timezone.now(),
        submitted_at=timezone.now(),
        score=1,
    )
    client = Client()
    client.force_login(examiner)

    monitoring = client.get(reverse("exam_monitoring", args=(exam.pk,)))
    results = client.get(reverse("exam_results", args=(exam.pk,)))

    assert monitoring.status_code == 200
    assert b"Attempts used" in monitoring.content
    assert results.status_code == 200
    assert str(attempt.attempt_number).encode() in results.content


@pytest.mark.django_db(transaction=True)
def test_concurrent_starts_create_only_one_attempt_on_postgresql(exam_setup):
    if connection.vendor != "postgresql":
        pytest.skip("SELECT FOR UPDATE concurrency requires PostgreSQL.")
    _examiner, candidate, exam, _enrollment, _question = exam_setup
    gate = Barrier(2)

    def start_in_separate_connection():
        close_old_connections()
        try:
            local_candidate = User.objects.get(pk=candidate.pk)
            local_exam = Exam.objects.get(pk=exam.pk)
            gate.wait(timeout=10)
            return start_attempt(local_candidate, local_exam).pk
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        attempt_ids = list(pool.map(lambda _index: start_in_separate_connection(), range(2)))

    assert attempt_ids[0] == attempt_ids[1]
    assert Attempt.objects.filter(candidate=candidate, exam=exam).count() == 1
