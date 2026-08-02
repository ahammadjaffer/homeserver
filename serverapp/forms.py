from django import forms

class ImageUploadForm(forms.Form):
    image = forms.ImageField(label="Select and image to upload")
