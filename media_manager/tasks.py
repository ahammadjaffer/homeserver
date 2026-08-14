import os
from io import BytesIO
from PIL import Image
from pillow_heif import register_heif_opener
from django.core.files.base import ContentFile
from huey.contrib.djhuey import db_task
from .models import MediaFile

# Register HEIF / HEIC image support for Pillow
register_heif_opener()


@db_task()
def generate_image_thumbnail(file_id):
    """
    Background Huey task to generate a 300x300 thumbnail for an image MediaFile.
    """
    try:
        media_file = MediaFile.objects.get(id=file_id)
    except MediaFile.DoesNotExist:
        return

    # Check if mime_type indicates an image
    if not media_file.mime_type or not media_file.mime_type.startswith('image/'):
        return

    if not media_file.file or not os.path.exists(media_file.file.path):
        return

    try:
        # Open original image file
        with Image.open(media_file.file.path) as img:
            img.thumbnail((300, 300))
            
            # Convert RGBA/P palette modes to RGB for JPEG compatibility
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            thumb_io = BytesIO()
            img.save(thumb_io, format='JPEG', quality=75, optimize=True)
            
            base_name = os.path.splitext(os.path.basename(media_file.filename))[0]
            thumb_filename = f"thumb_{base_name}.jpg"

            # Save generated thumbnail into file's ImageField
            media_file.thumbnail.save(thumb_filename, ContentFile(thumb_io.getvalue()), save=True)

    except Exception as e:
        print(f"Error generating thumbnail for MediaFile {file_id}: {e}")
