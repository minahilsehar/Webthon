from django import forms


class UserImportForm(forms.Form):
    csv_file = forms.FileField(
        label="CSV file",
        help_text="Maximum 512 KB and 20 user rows per upload.",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,text/csv"}),
    )

    def clean_csv_file(self):
        uploaded_file = self.cleaned_data["csv_file"]
        if not uploaded_file.name.lower().endswith(".csv"):
            raise forms.ValidationError("Choose a .csv file.")
        if uploaded_file.size > 512 * 1024:
            raise forms.ValidationError(
                "The file exceeds 512 KB. No rows were imported."
            )
        return uploaded_file
