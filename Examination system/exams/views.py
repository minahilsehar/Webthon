import json
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from .forms import EnrollmentForm, ExamForm, QuestionForm
from .models import Answer, Attempt, Enrollment, Exam
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


def role_required(role):
    def decorate(view):
        @login_required
        @wraps(view)
        def guarded(request, *args, **kwargs):
            if request.user.role != role:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return guarded

    return decorate


def _form_error(error):
    if isinstance(error, ValidationError):
        return "; ".join(error.messages)
    return str(error)


@role_required(User.Role.EXAMINER)
def examiner_dashboard(request):
    exams = Exam.objects.filter(owner=request.user).order_by("-created_at")
    return render(request, "exams/examiner_dashboard.html", {"exams": exams})


@role_required(User.Role.EXAMINER)
def create_exam(request):
    form = ExamForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        exam = form.save(commit=False)
        exam.owner = request.user
        exam.status = Exam.Status.DRAFT
        exam.save()
        return redirect("exam_manage", exam_id=exam.pk)
    return render(request, "exams/exam_form.html", {"form": form, "is_new": True})


@role_required(User.Role.EXAMINER)
def manage_exam(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id, owner=request.user)
    form = ExamForm(request.POST or None, instance=exam)
    if request.method == "POST" and form.is_valid():
        values = form.cleaned_data
        try:
            with transaction.atomic():
                locked_exam = update_exam_attempt_policy(
                    request.user,
                    exam,
                    max_attempts=values["max_attempts"],
                    scoring_policy=values["scoring_policy"],
                )
                locked_exam.title = values["title"]
                locked_exam.duration_minutes = values["duration_minutes"]
                locked_exam.opens_at = values["opens_at"]
                locked_exam.closes_at = values["closes_at"]
                locked_exam.status = values["status"]
                locked_exam.save(
                    update_fields=(
                        "title",
                        "duration_minutes",
                        "opens_at",
                        "closes_at",
                        "status",
                    )
                )
        except ValidationError as error:
            form.add_error(None, _form_error(error))
        else:
            return redirect("exam_manage", exam_id=exam.pk)
    enrollment_form = EnrollmentForm(exam=exam)
    return render(
        request,
        "exams/exam_manage.html",
        {
            "exam": exam,
            "form": form,
            "enrollment_form": enrollment_form,
            "questions": exam.questions.order_by("position", "pk"),
        },
    )


@role_required(User.Role.EXAMINER)
def add_question(request, exam_id):
    exam = get_object_or_404(
        Exam,
        pk=exam_id,
        owner=request.user,
        status=Exam.Status.DRAFT,
    )
    form = QuestionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        question = form.save(commit=False)
        question.exam = exam
        question.save()
        return redirect("exam_manage", exam_id=exam.pk)
    return render(
        request,
        "exams/question_form.html",
        {"exam": exam, "form": form},
    )


@role_required(User.Role.EXAMINER)
@require_POST
def enroll_candidate(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id, owner=request.user)
    form = EnrollmentForm(request.POST, exam=exam)
    if form.is_valid():
        form.save()
        return redirect("exam_manage", exam_id=exam.pk)
    return render(
        request,
        "exams/exam_manage.html",
        {
            "exam": exam,
            "form": ExamForm(instance=exam),
            "enrollment_form": form,
            "questions": exam.questions.order_by("position", "pk"),
        },
        status=400,
    )


def _enrollment_attempt_count():
    attempts = (
        Attempt.objects.filter(
            exam_id=OuterRef("exam_id"),
            candidate_id=OuterRef("candidate_id"),
            is_sandbox=False,
        )
        .order_by()
        .values("exam_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    return Coalesce(Subquery(attempts, output_field=IntegerField()), Value(0))


@role_required(User.Role.EXAMINER)
def exam_monitoring(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id, owner=request.user)
    enrollments = Enrollment.objects.filter(exam=exam).select_related("candidate")
    enrollments = enrollments.annotate(attempts_used=_enrollment_attempt_count())
    status_filter = request.GET.get("status", "")
    if status_filter in Attempt.Status.values:
        enrollments = enrollments.filter(
            candidate__exam_attempts__exam=exam,
            candidate__exam_attempts__status=status_filter,
            candidate__exam_attempts__is_sandbox=False,
        ).distinct()
    page = Paginator(enrollments.order_by("candidate__username"), 50).get_page(
        request.GET.get("page")
    )
    candidate_ids = [enrollment.candidate_id for enrollment in page.object_list]
    attempt_rows = Attempt.objects.filter(
        exam=exam,
        candidate_id__in=candidate_ids,
        is_sandbox=False,
    ).order_by("candidate_id", "attempt_number")
    attempts_by_candidate = {}
    for attempt in attempt_rows:
        attempts_by_candidate.setdefault(attempt.candidate_id, []).append(attempt)
    for enrollment in page.object_list:
        enrollment.attempt_rows = attempts_by_candidate.get(enrollment.candidate_id, [])
    return render(
        request,
        "exams/monitoring.html",
        {
            "exam": exam,
            "page": page,
            "status_filter": status_filter,
            "status_choices": Attempt.Status.choices,
        },
    )


@role_required(User.Role.EXAMINER)
def exam_results(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id, owner=request.user)
    attempts = Attempt.objects.filter(exam=exam, is_sandbox=False).select_related(
        "candidate"
    )
    status_filter = request.GET.get("status", "")
    if status_filter in Attempt.Status.values:
        attempts = attempts.filter(status=status_filter)
    candidate_filter = request.GET.get("candidate", "").strip()
    if candidate_filter:
        attempts = attempts.filter(candidate__username__icontains=candidate_filter)
    page = Paginator(
        attempts.order_by("candidate__username", "attempt_number"),
        50,
    ).get_page(request.GET.get("page"))
    candidate_ids = {attempt.candidate_id for attempt in page.object_list}
    scored_attempts = Attempt.objects.filter(
        exam=exam,
        candidate_id__in=candidate_ids,
        is_sandbox=False,
        score__isnull=False,
        status__in=(Attempt.Status.SUBMITTED, Attempt.Status.EXPIRED),
    ).order_by("candidate_id", "attempt_number")
    attempts_by_candidate = {}
    for attempt in scored_attempts:
        attempts_by_candidate.setdefault(attempt.candidate_id, []).append(attempt)
    used_counts = dict(
        Attempt.objects.filter(
            exam=exam,
            candidate_id__in=candidate_ids,
            is_sandbox=False,
        )
        .values("candidate_id")
        .annotate(total=Count("pk"))
        .values_list("candidate_id", "total")
    )
    counted_attempt_ids = set()
    for candidate_attempts in attempts_by_candidate.values():
        if exam.scoring_policy == Exam.ScoringPolicy.HIGHEST:
            counted = max(candidate_attempts, key=lambda attempt: (attempt.score, -attempt.attempt_number))
        elif exam.scoring_policy == Exam.ScoringPolicy.LATEST:
            counted = max(candidate_attempts, key=lambda attempt: (attempt.submitted_at, attempt.pk))
        else:
            counted = min(candidate_attempts, key=lambda attempt: attempt.attempt_number)
        counted_attempt_ids.add(counted.pk)
    for attempt in page.object_list:
        attempt.attempts_used = used_counts.get(attempt.candidate_id, 0)
    return render(
        request,
        "exams/results.html",
        {
            "exam": exam,
            "page": page,
            "status_filter": status_filter,
            "candidate_filter": candidate_filter,
            "status_choices": Attempt.Status.choices,
            "counted_attempt_ids": counted_attempt_ids,
        },
    )


@role_required(User.Role.EXAMINER)
@require_POST
def publish_results(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id, owner=request.user)
    publish_exam_results(request.user, exam)
    return redirect("exam_results", exam_id=exam.pk)


@role_required(User.Role.CANDIDATE)
def candidate_dashboard(request):
    enrollments = list(
        Enrollment.objects.filter(
            candidate=request.user,
            is_active=True,
            exam__status=Exam.Status.PUBLISHED,
        )
        .select_related("exam")
        .annotate(
            attempts_used=Count(
                "exam__attempts",
                filter=Q(
                    exam__attempts__candidate=request.user,
                    exam__attempts__is_sandbox=False,
                ),
                distinct=True,
            )
        )
        .order_by("exam__closes_at", "exam__title")
    )
    active_attempts = {
        attempt.exam_id: attempt
        for attempt in Attempt.objects.filter(
            candidate=request.user,
            status=Attempt.Status.IN_PROGRESS,
            is_sandbox=False,
            deadline__gt=timezone.now(),
        )
    }
    for enrollment in enrollments:
        enrollment.active_attempt = active_attempts.get(enrollment.exam_id)
        enrollment.attempts_remaining = max(
            0,
            enrollment.exam.max_attempts - enrollment.attempts_used,
        )
        enrollment.next_attempt_number = (
            enrollment.active_attempt.attempt_number
            if enrollment.active_attempt
            else min(enrollment.attempts_used + 1, enrollment.exam.max_attempts)
        )
    return render(request, "exams/candidate_dashboard.html", {"enrollments": enrollments})


@role_required(User.Role.CANDIDATE)
def exam_instructions(request, exam_id):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related("exam"),
        exam_id=exam_id,
        candidate=request.user,
        is_active=True,
        exam__status=Exam.Status.PUBLISHED,
    )
    exam = enrollment.exam
    active_attempt = Attempt.objects.filter(
        candidate=request.user,
        exam=exam,
        status=Attempt.Status.IN_PROGRESS,
        is_sandbox=False,
        deadline__gt=timezone.now(),
    ).first()
    attempts_used = Attempt.objects.filter(
        candidate=request.user,
        exam=exam,
        is_sandbox=False,
    ).count()
    return render(
        request,
        "exams/instructions.html",
        {
            "exam": exam,
            "active_attempt": active_attempt,
            "attempts_used": attempts_used,
            "attempts_remaining": max(0, exam.max_attempts - attempts_used),
            "next_attempt_number": (
                active_attempt.attempt_number
                if active_attempt
                else min(attempts_used + 1, exam.max_attempts)
            ),
        },
    )


@role_required(User.Role.CANDIDATE)
@require_POST
def begin_attempt(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    try:
        attempt = start_attempt(request.user, exam)
    except AttemptStartDenied as error:
        return render(
            request,
            "exams/error.html",
            {"message": str(error)},
            status=error.status_code,
        )
    return redirect("attempt_detail", attempt_id=attempt.pk)


@role_required(User.Role.CANDIDATE)
def attempt_detail(request, attempt_id):
    attempt = get_object_or_404(
        Attempt.objects.select_related("exam"),
        pk=attempt_id,
        candidate=request.user,
        is_sandbox=False,
    )
    answer_values = {
        answer.question_id: {"value": answer.value, "sequence": answer.sequence}
        for answer in Answer.objects.filter(attempt=attempt)
    }
    questions = [
        {
            "id": question.pk,
            "prompt": question.prompt,
            "options": question.options,
            "answer": answer_values.get(question.pk, {"value": [], "sequence": 0}),
        }
        for question in attempt.question_snapshots.all()
    ]
    return render(
        request,
        "exams/attempt.html",
        {
            "attempt": attempt,
            "questions": questions,
            "remaining_seconds": max(
                0,
                int((attempt.deadline - timezone.now()).total_seconds()),
            ),
        },
    )


@role_required(User.Role.CANDIDATE)
@require_POST
def autosave_answer(request, attempt_id):
    if request.content_type != "application/json":
        return JsonResponse({"error": "Send an application/json request."}, status=415)
    if len(request.body) > 32768:
        return JsonResponse({"error": "Answer payload is too large."}, status=413)
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)
    if not isinstance(payload, dict) or not {"question_id", "sequence", "value"} <= set(
        payload
    ):
        return JsonResponse({"error": "Answer payload is incomplete."}, status=400)
    if any(
        isinstance(payload[field], bool)
        or not isinstance(payload[field], int)
        or payload[field] < 1
        for field in ("question_id", "sequence")
    ):
        return JsonResponse({"error": "Question and sequence IDs must be positive integers."}, status=400)
    try:
        result = save_attempt_answer(
            request.user,
            attempt_id,
            payload["question_id"],
            payload["sequence"],
            payload["value"],
        )
    except AttemptSequenceConflict as error:
        return JsonResponse(
            {
                "error": str(error),
                "sequence": error.current_sequence,
                "saved": False,
            },
            status=409,
        )
    except (AttemptNotFound, AttemptClosed) as error:
        return JsonResponse({"error": str(error)}, status=error.status_code)
    except ValidationError as error:
        return JsonResponse({"error": _form_error(error)}, status=400)
    return JsonResponse(result)


@role_required(User.Role.CANDIDATE)
@require_POST
def attempt_heartbeat(request, attempt_id):
    try:
        attempt, remaining = heartbeat_attempt(request.user, attempt_id)
    except AttemptNotFound as error:
        return JsonResponse({"error": str(error)}, status=error.status_code)
    return JsonResponse({"status": attempt.status, "remaining_seconds": remaining})


@role_required(User.Role.CANDIDATE)
@require_POST
def submit_attempt(request, attempt_id):
    try:
        attempt = finish_attempt(request.user, attempt_id)
    except AttemptNotFound as error:
        return JsonResponse({"error": str(error)}, status=error.status_code)
    return redirect("attempt_history", exam_id=attempt.exam_id)


@role_required(User.Role.CANDIDATE)
def attempt_history(request, exam_id):
    exam = get_object_or_404(
        Exam.objects.filter(enrollments__candidate=request.user),
        pk=exam_id,
    )
    attempts = Attempt.objects.filter(
        candidate=request.user,
        exam=exam,
        is_sandbox=False,
    ).order_by("attempt_number")
    counted_attempt = official_attempt(request.user, exam) if exam.results_published else None
    return render(
        request,
        "exams/attempt_history.html",
        {
            "exam": exam,
            "attempts": attempts,
            "counted_attempt": counted_attempt,
        },
    )
