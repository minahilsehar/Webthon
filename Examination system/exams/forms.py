from django import forms

from apps.accounts.models import User
from .models import Enrollment, Exam, Question


class ExamForm(forms.ModelForm):
    max_attempts = forms.IntegerField(min_value=1, max_value=10, initial=1)
    duration_minutes = forms.IntegerField(min_value=1)

    class Meta:
        model = Exam
        fields = (
            "title",
            "duration_minutes",
            "opens_at",
            "closes_at",
            "max_attempts",
            "scoring_policy",
            "status",
        )
        widgets = {
            "opens_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "closes_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["max_attempts"].label = "Attempts allowed"
        self.fields["scoring_policy"].label = "Which score counts"
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "ui-input w-full px-3")

    def clean(self):
        cleaned_data = super().clean()
        opens_at = cleaned_data.get("opens_at")
        closes_at = cleaned_data.get("closes_at")
        if opens_at and closes_at and closes_at <= opens_at:
            self.add_error("closes_at", "The closing time must be after the opening time.")
        if (
            cleaned_data.get("status") == Exam.Status.PUBLISHED
            and self.instance.pk
            and not self.instance.questions.filter(is_active=True).exists()
        ):
            self.add_error("status", "Add at least one active question before publishing.")
        if cleaned_data.get("status") == Exam.Status.PUBLISHED and not self.instance.pk:
            self.add_error("status", "Save the draft and add a question before publishing.")
        return cleaned_data


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ("prompt", "options", "answer_key", "points", "position")
        widgets = {
            "options": forms.Textarea(attrs={"rows": 4}),
            "answer_key": forms.Textarea(attrs={"rows": 2}),
        }

    def clean(self):
        cleaned_data = super().clean()
        options = cleaned_data.get("options")
        answer_key = cleaned_data.get("answer_key")
        if not isinstance(options, list) or not options:
            self.add_error("options", "Enter a non-empty JSON list of answer options.")
        elif not all(isinstance(option, str) for option in options):
            self.add_error("options", "Answer options must be text values.")
        elif not isinstance(answer_key, list) or not answer_key:
            self.add_error("answer_key", "Enter a non-empty JSON list for the correct answer.")
        elif not all(isinstance(answer, str) for answer in answer_key):
            self.add_error("answer_key", "Correct answers must be text values.")
        elif any(answer not in options for answer in answer_key):
            self.add_error("answer_key", "Every correct answer must be one of the options.")
        return cleaned_data


class EnrollmentForm(forms.Form):
    candidate_username = forms.CharField(max_length=150)

    def __init__(self, *args, exam, **kwargs):
        self.exam = exam
        super().__init__(*args, **kwargs)

    def clean_candidate_username(self):
        username = self.cleaned_data["candidate_username"]
        try:
            return User.objects.get(
                username=username,
                role=User.Role.CANDIDATE,
                is_active=True,
            )
        except User.DoesNotExist as error:
            raise forms.ValidationError(
                "Enter the username of an active candidate account."
            ) from error

    def save(self):
        enrollment, created = Enrollment.objects.get_or_create(
            exam=self.exam,
            candidate=self.cleaned_data["candidate_username"],
            defaults={"is_active": True},
        )
        if not created and not enrollment.is_active:
            enrollment.is_active = True
            enrollment.save(update_fields=("is_active",))
        return enrollment
