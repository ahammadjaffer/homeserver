import json
import os
import mimetypes
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Sum
from django.core.cache import cache
from django.conf import settings

from .forms import SignUpForm, LoginForm
from .models import Folder, MediaFile
from .signals import get_folder_cache_key, invalidate_user_folder_cache
from .tasks import generate_image_thumbnail


# Helper to parse JSON or POST data from request
def get_request_data(request):
    if request.content_type == 'application/json':
        try:
            return json.loads(request.body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
    if request.body:
        try:
            return json.loads(request.body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    return request.POST


# --- AUTHENTICATION VIEWS ---

def signup_view(request):
    if request.user.is_authenticated:
        return redirect('list_images')

    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome to NitroStream, {user.username}!")
            return redirect('list_images')
    else:
        form = SignUpForm()

    return render(request, 'media_manager/signup.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('list_images')

    next_url = request.GET.get('next', 'list_images')

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f"Welcome back, {user.username}!")
                return redirect(request.POST.get('next') or 'list_images')
            else:
                messages.error(request, "Invalid username or password.")
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = LoginForm()

    return render(request, 'media_manager/login.html', {'form': form, 'next': next_url})


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('login')


# --- FOLDER MANAGEMENT REST API ---

@login_required
@require_http_methods(["POST"])
def create_folder(request):
    data = get_request_data(request)
    name = data.get('name', '').strip()
    parent_id = data.get('parent_id')

    if not name:
        return JsonResponse({'error': 'Folder name is required.'}, status=400)

    parent = None
    if parent_id:
        try:
            parent = Folder.objects.get(id=parent_id, owner=request.user)
        except Folder.DoesNotExist:
            return JsonResponse({'error': 'Parent folder not found.'}, status=404)

    # Collision check under the same parent for the current user
    if Folder.objects.filter(owner=request.user, parent=parent, name__iexact=name).exists():
        return JsonResponse({'error': 'A folder with this name already exists in this directory.'}, status=400)

    folder = Folder.objects.create(
        name=name,
        parent=parent,
        owner=request.user
    )

    invalidate_user_folder_cache(request.user.id)

    return JsonResponse({
        'success': True,
        'folder': {
            'id': folder.id,
            'name': folder.name,
            'parent_id': folder.parent_id,
            'created_at': folder.created_at.isoformat()
        }
    }, status=201)


@login_required
@require_http_methods(["PATCH", "POST"])
def rename_folder(request, folder_id):
    data = get_request_data(request)
    new_name = data.get('name', '').strip()

    if not new_name:
        return JsonResponse({'error': 'New folder name is required.'}, status=400)

    try:
        folder = Folder.objects.get(id=folder_id, owner=request.user)
    except Folder.DoesNotExist:
        return JsonResponse({'error': 'Folder not found.'}, status=404)

    # Collision check under the same parent
    if Folder.objects.filter(owner=request.user, parent=folder.parent, name__iexact=new_name).exclude(id=folder.id).exists():
        return JsonResponse({'error': 'A folder with this name already exists in this directory.'}, status=400)

    folder.name = new_name
    folder.save()

    invalidate_user_folder_cache(request.user.id)

    return JsonResponse({
        'success': True,
        'folder': {
            'id': folder.id,
            'name': folder.name,
            'parent_id': folder.parent_id
        }
    })


@login_required
@require_http_methods(["DELETE", "POST"])
def delete_folder(request, folder_id):
    try:
        folder = Folder.objects.get(id=folder_id, owner=request.user)
    except Folder.DoesNotExist:
        return JsonResponse({'error': 'Folder not found.'}, status=404)

    folder.delete()

    invalidate_user_folder_cache(request.user.id)

    return JsonResponse({
        'success': True,
        'message': 'Folder deleted successfully.'
    })


@login_required
@require_http_methods(["GET"])
def get_folder_tree(request):
    cache_key = get_folder_cache_key(request.user.id)
    cached_tree = cache.get(cache_key)

    if cached_tree is not None:
        return JsonResponse({
            'success': True,
            'tree': cached_tree,
            'cached': True
        })

    # Query all folders for the authenticated user with file count annotation
    folders = Folder.objects.filter(owner=request.user).annotate(file_count=Count('files')).order_by('name')

    folder_map = {}
    root_folders = []

    for f in folders:
        folder_map[f.id] = {
            'id': f.id,
            'name': f.name,
            'parent_id': f.parent_id,
            'created_at': f.created_at.isoformat(),
            'file_count': f.file_count,
            'subfolders': []
        }

    for f in folders:
        node = folder_map[f.id]
        if f.parent_id and f.parent_id in folder_map:
            folder_map[f.parent_id]['subfolders'].append(node)
        else:
            root_folders.append(node)

    # Store tree in Redis cache for 24 hours (86400s)
    cache.set(cache_key, root_folders, timeout=86400)

    return JsonResponse({
        'success': True,
        'tree': root_folders,
        'cached': False
    })


# --- FILE UPLOAD & STREAMING API ---

@login_required
@require_http_methods(["POST"])
def upload_media_file(request):
    """
    AJAX endpoint to handle user file uploads.
    Creates a MediaFile record ensuring owner=request.user and triggers thumbnail generation in background.
    """
    if 'file' not in request.FILES:
        return JsonResponse({'error': 'No file provided.'}, status=400)

    uploaded_file = request.FILES['file']
    folder_id = request.POST.get('folder_id')

    folder = None
    if folder_id:
        try:
            folder = Folder.objects.get(id=folder_id, owner=request.user)
        except Folder.DoesNotExist:
            return JsonResponse({'error': 'Target folder not found.'}, status=404)

    mime_type, _ = mimetypes.guess_type(uploaded_file.name)
    if not mime_type:
        mime_type = uploaded_file.content_type or 'application/octet-stream'

    media_file = MediaFile.objects.create(
        owner=request.user,
        folder=folder,
        file=uploaded_file,
        filename=uploaded_file.name,
        file_size=uploaded_file.size,
        mime_type=mime_type
    )

    # Immediately trigger Huey background thumbnail generation
    generate_image_thumbnail(media_file.id)

    return JsonResponse({
        'success': True,
        'file': {
            'id': media_file.id,
            'filename': media_file.filename,
            'file_size': media_file.file_size,
            'mime_type': media_file.mime_type,
            'folder_id': media_file.folder_id,
            'created_at': media_file.created_at.isoformat()
        }
    }, status=201)


@login_required
@require_http_methods(["GET", "HEAD"])
def stream_media(request, file_id):
    """
    Secure media streaming endpoint using Nginx X-Accel-Redirect.
    Authenticates user ownership, then offloads media delivery & byte-range seeking to Nginx.
    """
    try:
        media_file = MediaFile.objects.get(id=file_id, owner=request.user)
    except MediaFile.DoesNotExist:
        raise Http404("Media file not found or access denied.")

    if not media_file.file:
        raise Http404("File content missing.")

    # Format relative path for Nginx internal location mapping
    relative_path = str(media_file.file.name).replace('\\', '/').lstrip('/')
    x_accel_path = f"/protected_media/{relative_path}"

    response = HttpResponse(content_type=media_file.mime_type)
    response['X-Accel-Redirect'] = x_accel_path
    response['Content-Disposition'] = f'inline; filename="{media_file.filename}"'
    return response


# --- DRIVE VIEW (SPA Shell) ---

@login_required
def drive_view(request):
    """Renders the Google Drive-style SPA shell."""
    used_bytes = MediaFile.objects.filter(owner=request.user).aggregate(
        total=Sum('file_size')
    )['total'] or 0
    quota_mb = getattr(request.user, 'storage_quota_mb', 5000)

    return render(request, 'media_manager/drive.html', {
        'used_bytes': used_bytes,
        'storage_quota_mb': quota_mb,
    })


# --- FOLDER CONTENTS API ---

@login_required
@require_http_methods(["GET"])
def get_folder_contents(request, folder_id=None):
    """
    Returns subfolders and files for a given folder (or root if folder_id is None).
    This is the core API powering folder navigation in the drive UI.
    """
    folder = None
    breadcrumbs = [{"id": None, "name": "My Drive"}]

    if folder_id is not None:
        try:
            folder = Folder.objects.get(id=folder_id, owner=request.user)
        except Folder.DoesNotExist:
            return JsonResponse({'error': 'Folder not found.'}, status=404)

        # Build breadcrumb chain by walking up parent chain
        chain = []
        node = folder
        while node:
            chain.append({"id": node.id, "name": node.name})
            node = node.parent
        breadcrumbs += reversed(chain)

    # Subfolders in this directory
    subfolders = Folder.objects.filter(
        owner=request.user, parent=folder
    ).annotate(file_count=Count('files')).order_by('name')

    # Files in this directory
    files = MediaFile.objects.filter(
        owner=request.user, folder=folder
    ).order_by('-created_at')

    def thumb_url(mf):
        if mf.thumbnail:
            return request.build_absolute_uri(mf.thumbnail.url)
        return None

    def file_icon(mime):
        if mime and mime.startswith('image/'): return 'image'
        if mime and mime.startswith('video/'): return 'video'
        if mime and mime.startswith('audio/'): return 'audio'
        if mime == 'application/pdf': return 'pdf'
        return 'file'

    return JsonResponse({
        'success': True,
        'folder': {'id': folder.id, 'name': folder.name, 'parent_id': folder.parent_id} if folder else None,
        'breadcrumbs': list(breadcrumbs),
        'folders': [
            {
                'id': f.id,
                'name': f.name,
                'parent_id': f.parent_id,
                'file_count': f.file_count,
                'created_at': f.created_at.isoformat(),
            }
            for f in subfolders
        ],
        'files': [
            {
                'id': mf.id,
                'filename': mf.filename,
                'file_size': mf.file_size,
                'mime_type': mf.mime_type,
                'icon_type': file_icon(mf.mime_type),
                'thumbnail_url': thumb_url(mf),
                'stream_url': f'/stream/{mf.id}/',
                'created_at': mf.created_at.isoformat(),
            }
            for mf in files
        ],
    })


# --- FILE MANAGEMENT API ---

@login_required
@require_http_methods(["POST", "DELETE"])
def delete_media_file(request, file_id):
    """Deletes a MediaFile record, its file on disk, and its thumbnail."""
    try:
        media_file = MediaFile.objects.get(id=file_id, owner=request.user)
    except MediaFile.DoesNotExist:
        return JsonResponse({'error': 'File not found.'}, status=404)

    # Delete physical file from disk
    if media_file.file:
        try:
            file_path = media_file.file.path
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass

    # Delete thumbnail from disk
    if media_file.thumbnail:
        try:
            thumb_path = media_file.thumbnail.path
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
        except Exception:
            pass

    media_file.delete()
    invalidate_user_folder_cache(request.user.id)

    return JsonResponse({'success': True})


@login_required
@require_http_methods(["POST", "PATCH"])
def rename_media_file(request, file_id):
    """Renames a MediaFile's display filename."""
    try:
        media_file = MediaFile.objects.get(id=file_id, owner=request.user)
    except MediaFile.DoesNotExist:
        return JsonResponse({'error': 'File not found.'}, status=404)

    data = get_request_data(request)
    new_name = data.get('filename', '').strip()
    if not new_name:
        return JsonResponse({'error': 'Filename is required.'}, status=400)

    media_file.filename = new_name
    media_file.save(update_fields=['filename'])

    return JsonResponse({
        'success': True,
        'file': {'id': media_file.id, 'filename': media_file.filename}
    })


@login_required
@require_http_methods(["POST", "PATCH"])
def move_media_file(request, file_id):
    """Moves a MediaFile to a different folder (or to root if folder_id is null)."""
    try:
        media_file = MediaFile.objects.get(id=file_id, owner=request.user)
    except MediaFile.DoesNotExist:
        return JsonResponse({'error': 'File not found.'}, status=404)

    data = get_request_data(request)
    folder_id = data.get('folder_id')

    target_folder = None
    if folder_id:
        try:
            target_folder = Folder.objects.get(id=folder_id, owner=request.user)
        except Folder.DoesNotExist:
            return JsonResponse({'error': 'Target folder not found.'}, status=404)

    media_file.folder = target_folder
    media_file.save(update_fields=['folder'])
    invalidate_user_folder_cache(request.user.id)

    return JsonResponse({'success': True})
