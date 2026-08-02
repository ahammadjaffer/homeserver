import os
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.conf import settings
from .forms import ImageUploadForm

def hello_world(request):
    return HttpResponse("Hello world!!")

def list_images(request):
    image_dir = settings.MEDIA_ROOT

    # Ensure the directory exists
    if not os.path.exists(image_dir):
        os.makedirs(image_dir)

    # Handle File Upload (POST request)
    if request.method == 'POST':
        form = ImageUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES['image']
            save_path = os.path.join(image_dir, uploaded_file.name)

            # Write file chunks to media directory
            with open(save_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
                
            return redirect('list_images')

    else:
        form = ImageUploadForm()

    # List all valid image files
    valid_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.heif')
    images = [
        f for f in os.listdir(image_dir)
        if os.path.isfile(os.path.join(image_dir, f)) and f.lower().endswith(valid_extensions)
    ]

    return render(request, 'serverapp/image_list.html', {
        'form': form,
        'images': images,
        'MEDIA_URL': settings.MEDIA_URL
    })