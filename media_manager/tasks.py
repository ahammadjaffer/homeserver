import os
import shutil
import subprocess
from io import BytesIO
from PIL import Image
from pillow_heif import register_heif_opener
from django.core.files.base import ContentFile
from huey.contrib.djhuey import db_task
from .models import MediaFile

# Register HEIF / HEIC image support for Pillow
register_heif_opener()


def get_ffmpeg_bin():
    """Locates FFmpeg executable across system PATH, imageio-ffmpeg, or common installation paths."""
    exe = shutil.which('ffmpeg')
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    for p in [r"C:\ffmpeg\bin\ffmpeg.exe", r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"]:
        if os.path.exists(p):
            return p
    return 'ffmpeg'


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


@db_task()
def generate_video_preview(file_id):
    """
    Background Huey task to generate:
    1. A static poster thumbnail (if missing) from video frame.
    2. A low-bitrate animated WebP hover preview strip via FFmpeg (with NVENC/CUDA hardware acceleration fallback).
    """
    try:
        media_file = MediaFile.objects.get(id=file_id)
    except MediaFile.DoesNotExist:
        return

    if not media_file.mime_type or not media_file.mime_type.startswith('video/'):
        return

    if not media_file.file or not os.path.exists(media_file.file.path):
        return

    ffmpeg_bin = get_ffmpeg_bin()
    input_path = media_file.file.path
    base_name = os.path.splitext(os.path.basename(media_file.filename))[0]
    updated = False

    # --- 1. Static Poster Thumbnail Generation ---
    if not media_file.thumbnail or not os.path.exists(media_file.thumbnail.path):
        try:
            thumb_cmd = [
                ffmpeg_bin, '-y',
                '-ss', '00:00:01',
                '-i', input_path,
                '-vframes', '1',
                '-vf', 'scale=320:-2',
                '-q:v', '3',
                '-f', 'image2',
                '-'
            ]
            res = subprocess.run(thumb_cmd, capture_output=True, check=False)
            if res.returncode == 0 and res.stdout:
                thumb_filename = f"thumb_{base_name}.jpg"
                media_file.thumbnail.save(thumb_filename, ContentFile(res.stdout), save=False)
                updated = True
            else:
                fallback_cmd = [
                    ffmpeg_bin, '-y',
                    '-i', input_path,
                    '-vframes', '1',
                    '-vf', 'scale=320:-2',
                    '-q:v', '3',
                    '-f', 'image2',
                    '-'
                ]
                res2 = subprocess.run(fallback_cmd, capture_output=True, check=False)
                if res2.returncode == 0 and res2.stdout:
                    thumb_filename = f"thumb_{base_name}.jpg"
                    media_file.thumbnail.save(thumb_filename, ContentFile(res2.stdout), save=False)
                    updated = True
        except Exception as e:
            print(f"Error generating static video thumbnail for MediaFile {file_id}: {e}")

    # --- 2. Low-bitrate Animated WebP Hover / Scrubbing Strip ---
    try:
        preview_bytes = None
        
        # 2a. Attempt hardware accelerated decoding with CUDA / NVENC
        hw_cmd = [
            ffmpeg_bin, '-y',
            '-hwaccel', 'cuda',
            '-ss', '00:00:01',
            '-t', '5',
            '-i', input_path,
            '-vf', 'fps=2,scale=320:-2:flags=lanczos',
            '-c:v', 'libwebp',
            '-lossless', '0',
            '-q:v', '45',
            '-loop', '0',
            '-an',
            '-f', 'webp',
            '-'
        ]
        try:
            res_hw = subprocess.run(hw_cmd, capture_output=True, check=False)
            if res_hw.returncode == 0 and res_hw.stdout:
                preview_bytes = res_hw.stdout
        except Exception:
            pass

        # 2b. Standard CPU fallback
        if not preview_bytes:
            preview_cmd = [
                ffmpeg_bin, '-y',
                '-ss', '00:00:01',
                '-t', '5',
                '-i', input_path,
                '-vf', 'fps=2,scale=320:-2:flags=lanczos',
                '-c:v', 'libwebp',
                '-lossless', '0',
                '-q:v', '45',
                '-loop', '0',
                '-an',
                '-f', 'webp',
                '-'
            ]
            res_sw = subprocess.run(preview_cmd, capture_output=True, check=False)
            if res_sw.returncode == 0 and res_sw.stdout:
                preview_bytes = res_sw.stdout
            else:
                fallback_preview_cmd = [
                    ffmpeg_bin, '-y',
                    '-i', input_path,
                    '-t', '4',
                    '-vf', 'fps=2,scale=320:-2:flags=lanczos',
                    '-c:v', 'libwebp',
                    '-lossless', '0',
                    '-q:v', '45',
                    '-loop', '0',
                    '-an',
                    '-f', 'webp',
                    '-'
                ]
                res_fb = subprocess.run(fallback_preview_cmd, capture_output=True, check=False)
                if res_fb.returncode == 0 and res_fb.stdout:
                    preview_bytes = res_fb.stdout

        if preview_bytes:
            preview_filename = f"preview_{base_name}.webp"
            media_file.hover_preview.save(preview_filename, ContentFile(preview_bytes), save=False)
            updated = True
            
    except Exception as e:
        print(f"Error generating animated hover preview for MediaFile {file_id}: {e}")

    if updated:
        media_file.save()

