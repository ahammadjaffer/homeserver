import os
from PIL import Image
from pillow_heif import register_heif_opener
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.views.decorators.http import require_POST
from .forms import FileUploadForm
from django.views.decorators.clickjacking import xframe_options_exempt

# Register HEIC support for Pillow
register_heif_opener()

# Define common extensions for categorization
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.heic', '.heif')
VIDEO_EXTS = ('.mp4', '.mov', '.m4v', '.avi', '.mkv', '.webm')
# Anything else automatically drops into the 'files' category

def get_category(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext in IMAGE_EXTS:
        return 'images'
    elif ext in VIDEO_EXTS:
        return 'videos'
    return 'files'

def create_thumbnail(image_path, thumb_path, size=(300, 300)):
    """Generates a compressed 300x300 thumbnail for images and HEIC files."""
    try:
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        with Image.open(image_path) as img:
            img.thumbnail(size)
            # Convert RGBA/P modes to RGB before saving as JPEG
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(thumb_path, "JPEG", quality=75, optimize=True)
            return True
    except Exception as e:
        print(f"Error generating thumbnail for {image_path}: {e}")
        return False

def list_images(request):
    media_root = settings.MEDIA_ROOT
    thumb_root = os.path.join(media_root, '.thumbnails')

    # Ensure base subdirectories exist
    for folder in ['images', 'videos', 'files']:
        os.makedirs(os.path.join(media_root, folder), exist_ok=True)

    # Handle File Upload (POST request)
    if request.method == 'POST':
        form = FileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            # Cleaned data now contains the list of validated files
            files = form.cleaned_data['file']
            
            for uploaded_file in files:
                category = get_category(uploaded_file.name)
                target_dir = os.path.join(media_root, category)
                save_path = os.path.join(target_dir, uploaded_file.name)

                # Save file to disk
                with open(save_path, 'wb+') as destination:
                    for chunk in uploaded_file.chunks():
                        destination.write(chunk)

                # Generate thumbnail if image
                ext = os.path.splitext(uploaded_file.name)[1].lower()
                if ext in IMAGE_EXTS:
                    thumb_path = os.path.join(thumb_root, category, f"{os.path.splitext(uploaded_file.name)[0]}.jpg")
                    create_thumbnail(save_path, thumb_path)

            return redirect('list_images')

    else:
        form = FileUploadForm()

    # Dictionary to categorize media items
    grouped_media = {
        'images': [],
        'videos': [],
        'documents': []
    }

    for root, _, files in os.walk(media_root):
        # Skip thumbnail directory during scan
        if '.thumbnails' in root:
            continue

        for file in files:
            rel_dir = os.path.relpath(root, media_root)
            # Determine relative URL path (e.g. "images/photo.jpg")
            rel_path = file if rel_dir == '.' else os.path.join(rel_dir, file).replace('\\', '/')
            full_path = os.path.join(root, file)
            ext = os.path.splitext(file)[1].lower()

            item_data = {
                'name': file,
                'rel_path': rel_path,
                'url_path': f"{settings.MEDIA_URL}{rel_path}",
                'ext': ext
            }

            if ext in IMAGE_EXTS:
                # Check/Create thumbnail
                base_name = os.path.splitext(file)[0]
                thumb_relative = os.path.join('.thumbnails', rel_dir, f"{base_name}.jpg").replace('\\', '/')
                thumb_full = os.path.join(thumb_root, rel_dir, f"{base_name}.jpg")

                if not os.path.exists(thumb_full):
                    create_thumbnail(full_path, thumb_full)

                item_data['thumb_url'] = f"{settings.MEDIA_URL}{thumb_relative}" if os.path.exists(thumb_full) else item_data['url_path']
                grouped_media['images'].append(item_data)

            elif ext in VIDEO_EXTS:
                grouped_media['videos'].append(item_data)

            else:
                grouped_media['documents'].append(item_data)

    return render(request, 'serverapp/image_list.html', {
        'form': form,
        'grouped_media': grouped_media,
    })

@require_POST
def delete_file(request):
    """Deletes a file and its associated thumbnail from disk."""
    file_rel_path = request.POST.get('file_rel_path')
    if file_rel_path:
        media_root = settings.MEDIA_ROOT

        # Prevent directory traversal attacks
        safe_rel_path = os.path.normpath(file_rel_path).lstrip('/\\')
        target_file = os.path.join(media_root, safe_rel_path)

        # Delete original file
        if os.path.exists(target_file) and target_file.startswith(media_root):
            os.remove(target_file)

        # Delete thumbnail if it exists
        dir_name, file_name = os.path.split(safe_rel_path)
        base_name = os.path.splitext(file_name)[0]
        thumb_file = os.path.join(media_root, '.thumbnails', dir_name, f"{base_name}.jpg")
        if os.path.exists(thumb_file):
            os.remove(thumb_file)

    return redirect('list_images')

@require_POST
def upload_single_file(request):
    """Processes a single file upload asynchronously via AJAX."""
    if 'file' not in request.FILES:
        return JsonResponse({'success': False, 'error': 'No file uploaded'}, status=400)

    uploaded_file = request.FILES['file']
    media_root = settings.MEDIA_ROOT
    thumb_root = os.path.join(media_root, '.thumbnails')

    try:
        category = get_category(uploaded_file.name)
        target_dir = os.path.join(media_root, category)
        os.makedirs(target_dir, exist_ok=True)
        
        save_path = os.path.join(target_dir, uploaded_file.name)

        # Save stream chunks
        with open(save_path, 'wb+') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)

        # Generate thumbnail if image
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext in IMAGE_EXTS:
            thumb_path = os.path.join(thumb_root, category, f"{os.path.splitext(uploaded_file.name)[0]}.jpg")
            create_thumbnail(save_path, thumb_path)

        return JsonResponse({
            'success': True,
            'filename': uploaded_file.name,
            'category': category
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)