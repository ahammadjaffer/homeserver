from django import forms

# Custom widget to allow selecting multiple files in HTML
class MultipleFileInput(forms.FileInput):
    allow_multiple_selected = True

# Custom field to handle validating multiple files at once
class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={'multiple': True}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = [single_file_clean(data, initial)]
        return result

class FileUploadForm(forms.Form):
    file = MultipleFileField(label="Select file(s) to upload")