from django.urls import path

from .controllers import exams as views

urlpatterns = [
    path("", views.candidate_dashboard, name="candidate_dashboard"),
    path("manage/", views.examiner_dashboard, name="examiner_dashboard"),
    path("manage/candidates/", views.candidate_directory, name="candidate_directory"),
    path("manage/new/", views.create_exam, name="exam_create"),
    path("manage/<int:exam_id>/", views.manage_exam, name="exam_manage"),
    path(
        "manage/<int:exam_id>/questions/new/",
        views.add_question,
        name="question_add",
    ),
    path(
        "manage/<int:exam_id>/enroll/",
        views.enroll_candidate,
        name="candidate_enroll",
    ),
    path(
        "manage/<int:exam_id>/monitoring/",
        views.exam_monitoring,
        name="exam_monitoring",
    ),
    path(
        "manage/<int:exam_id>/results/",
        views.exam_results,
        name="exam_results",
    ),
    path(
        "manage/<int:exam_id>/results/publish/",
        views.publish_results,
        name="results_publish",
    ),
    path("<int:exam_id>/instructions/", views.exam_instructions, name="instructions"),
    path("<int:exam_id>/start/", views.begin_attempt, name="attempt_start"),
    path(
        "<int:exam_id>/history/",
        views.attempt_history,
        name="attempt_history",
    ),
    path("attempt/<int:attempt_id>/", views.attempt_detail, name="attempt_detail"),
    path(
        "attempt/<int:attempt_id>/answers/",
        views.autosave_answer,
        name="answer_autosave",
    ),
    path(
        "attempt/<int:attempt_id>/heartbeat/",
        views.attempt_heartbeat,
        name="attempt_heartbeat",
    ),
    path(
        "attempt/<int:attempt_id>/submit/",
        views.submit_attempt,
        name="attempt_submit",
    ),
]
