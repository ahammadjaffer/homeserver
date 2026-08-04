import os
import subprocess
from pathlib import Path
from PIL import Image
from pillow_heif import register_heif_opener
from huey.contrib.djhuey import task

register_heif_opener()

def get_ffmpeg_video_encoder():
    """Detects NVIDIA NVENC (GTX 1080) vs CPU fallback."""
    try:
        result = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True, check=True)
        if 'h264_nvenc' in result.stdout:
            return 'h264_nvenc'
    except Exception:
        pass
    return 'libx264'

@task()
def process_file_background(save_path_str: str, category: str, media_root: str, thumb_root: str):
    """
    Background Task:
    1. Converts HEIC -> JPG or MKV -> MP4
    2. Deletes raw file
    3. Generates thumbnail for the converted image/video
    """
    file_path = Path(save_path_str)
    ext = file_path.suffix.lower()

    # Import create_thumbnail locally or from your utils module
    from .views import create_thumbnail  # adjust to wherever create_thumbnail is defined

    # --- A. Handle iPhone HEIC Photos ---
    if ext in ['.heic', '.heif']:
        jpg_path = file_path.with_suffix('.jpg')
        
        with Image.open(file_path) as img:
            rgb_img = img.convert('RGB')
            rgb_img.save(jpg_path, 'JPEG', quality=88, optimize=True)

        # Delete raw .heic file
        if file_path.exists():
            os.remove(file_path)

        # Create thumbnail for the new JPG
        thumb_path = os.path.join(thumb_root, category, f"{jpg_path.stem}.jpg")
        create_thumbnail(str(jpg_path), thumb_path)

    # --- B. Handle MKV Videos ---
    elif ext == '.mkv':
        pass
        # mp4_path = file_path.with_suffix('.mp4')
        # encoder = get_ffmpeg_video_encoder()
        # preset = 'fast' if encoder == 'h264_nvenc' else 'ultrafast'

        # cmd = [
        #     'ffmpeg', '-y',
        #     '-i', str(file_path),
        #     '-c:v', encoder,
        #     '-preset', preset,
        #     '-c:a', 'aac',
        #     '-movflags', '+faststart',
        #     str(mp4_path)
        # ]
        
        # subprocess.run(cmd, check=True)

        # # Delete raw .mkv file
        # if file_path.exists():
        #     os.remove(file_path)

        # # Optional: Generate video thumbnail from MP4 frame using FFmpeg
        # thumb_path = os.path.join(thumb_root, category, f"{mp4_path.stem}.jpg")
        # os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        
        # ffmpeg_thumb_cmd = [
        #     'ffmpeg', '-y',
        #     '-ss', '00:00:01',
        #     '-i', str(mp4_path),
        #     '-vframes', '1',
        #     '-q:v', '2',
        #     thumb_path
        # ]
        # subprocess.run(ffmpeg_thumb_cmd, stderr=subprocess.DEVNULL)