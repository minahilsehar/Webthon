from django import forms

from ..models import Degree, Department, Subject, User


class ProfileNameForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name")


class ProfileDepartmentForm(forms.Form):
    department = forms.ModelChoiceField(
        queryset=Department.objects.order_by("name"),
        required=False,
        empty_label="Not assigned",
    )


class ProfileDegreesForm(forms.Form):
    degrees = forms.ModelMultipleChoiceField(
        queryset=Degree.objects.order_by("name"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )


class ProfileSubjectsForm(forms.Form):
    subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.order_by("name"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )


class ProfilePhotoForm(forms.Form):
    image = forms.ImageField(
        label="Profile photo",
        widget=forms.ClearableFileInput(
            attrs={"accept": "image/jpeg,image/png,image/webp"}
        ),
    )
