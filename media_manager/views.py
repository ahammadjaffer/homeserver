import json
import os
import mimetypes
import urllib.parse
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Sum, Q
from django.core.cache import cache
from django.conf import settings

from .forms import SignUpForm, LoginForm
from .models import Folder, MediaFile
from .signals import get_folder_cache_key, invalidate_user_folder_cache
from .tasks import generate_image_thumbnail


# Module-level helper functions for UI serialization
def get_file_icon(mime):
    if mime and mime.startswith('image/'): return 'image'
    if mime and mime.startswith('video/'): return 'video'
    if mime and mime.startswith('audio/'): return 'audio'
    if mime == 'application/pdf': return 'pdf'
    return 'file'


def build_thumb_url(request, media_file):
    if media_file.thumbnail:
        return request.build_absolute_uri(media_file.thumbnail.url)
    return None


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


def get_all_descendant_folder_ids(root_folder):
    folder_ids = [root_folder.id]
    subfolders = list(Folder.objects.filter(parent=root_folder))
    for sf in subfolders:
        folder_ids.extend(get_all_descendant_folder_ids(sf))
    return folder_ids


@login_required
@require_http_methods(["DELETE", "POST"])
def delete_folder(request, folder_id):
    try:
        folder = Folder.objects.get(id=folder_id, owner=request.user)
    except Folder.DoesNotExist:
        return JsonResponse({'error': 'Folder not found.'}, status=404)

    # 1. Gather all descendant folder IDs
    all_folder_ids = get_all_descendant_folder_ids(folder)

    # 2. Delete physical files and thumbnails from disk for all contained MediaFiles
    media_files = MediaFile.objects.filter(folder_id__in=all_folder_ids, owner=request.user)
    for media_file in media_files:
        if media_file.file:
            try:
                file_path = media_file.file.path
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass
        if media_file.thumbnail:
            try:
                thumb_path = media_file.thumbnail.path
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)
            except Exception:
                pass

    # 3. Delete folder (CASCADE handles DB records)
    folder.delete()

    invalidate_user_folder_cache(request.user.id)

    return JsonResponse({
        'success': True,
        'message': 'Folder and all contained files deleted successfully.'
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

    safe_filename = os.path.basename(uploaded_file.name)
    mime_type, _ = mimetypes.guess_type(safe_filename)
    if not mime_type:
        mime_type = uploaded_file.content_type or 'application/octet-stream'

    media_file = MediaFile.objects.create(
        owner=request.user,
        folder=folder,
        file=uploaded_file,
        filename=safe_filename,
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


# --- SECURITY HELPERS FOR SHARING & ACCESS CONTROL ---

def is_descendant_of(folder, ancestor_folder):
    """
    Recursively verifies if folder is equal to or a child/grandchild of ancestor_folder.
    Prevents directory traversal / unauthorized access outside shared folder subtrees.
    """
    if not folder or not ancestor_folder:
        return False
    node = folder
    while node:
        if node.id == ancestor_folder.id:
            return True
        node = node.parent
    return False


def get_ancestor_folder_ids(folder):
    ancestors = []
    node = folder
    while node:
        ancestors.append(node.id)
        node = node.parent
    return ancestors


def user_has_share_access_to_folder(user, folder):
    """
    Checks if a user has access to a Folder (or any of its parent folders).
    Optimized single-query check across all ancestors.
    """
    if not user or not user.is_authenticated:
        return False
    if folder.owner == user:
        return True

    ancestor_ids = get_ancestor_folder_ids(folder)
    if not ancestor_ids:
        return False

    return Folder.objects.filter(
        id__in=ancestor_ids
    ).filter(
        Q(share_mode='link') |
        Q(is_shared=True, share_mode='private') |
        Q(share_mode='restricted', shared_users=user)
    ).exists()


def user_has_share_access_to_file(user, media_file):
    """
    Checks if a user has access to a MediaFile.
    Access granted if:
    1. User is the owner.
    2. File share_mode is 'link'.
    3. File share_mode is 'restricted' AND user in media_file.shared_users.
    4. Any parent folder in ancestor chain grants share access.
    """
    if not user or not user.is_authenticated:
        return False
    if media_file.owner == user:
        return True

    # Check file level
    if media_file.share_mode == 'link' or (media_file.is_shared and media_file.share_mode == 'private'):
        return True
    if media_file.share_mode == 'restricted' and media_file.shared_users.filter(id=user.id).exists():
        return True

    if media_file.folder:
        return user_has_share_access_to_folder(user, media_file.folder)

    return False


@login_required
@require_http_methods(["GET", "HEAD"])
def stream_media(request, file_id):
    """
    Secure media streaming endpoint using Nginx X-Accel-Redirect.
    Verifies user ownership or valid active share authorization before offloading to Nginx sendfile.
    Sanitizes HTTP Content-Disposition header to prevent header injection.
    """
    try:
        media_file = MediaFile.objects.get(id=file_id)
    except MediaFile.DoesNotExist:
        raise Http404("Media file not found.")

    if not user_has_share_access_to_file(request.user, media_file):
        raise Http404("Media file not found or access denied.")

    if not media_file.file:
        raise Http404("File content missing.")

    relative_path = str(media_file.file.name).replace('\\', '/').lstrip('/')
    x_accel_path = f"/protected_media/{relative_path}"

    safe_filename = media_file.filename.replace('\r', '').replace('\n', '').replace('"', "'")
    encoded_filename = urllib.parse.quote(safe_filename)

    response = HttpResponse(content_type=media_file.mime_type)
    response['X-Accel-Redirect'] = x_accel_path
    response['Content-Disposition'] = f'inline; filename="{safe_filename}"; filename*=UTF-8\'\'{encoded_filename}'
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
    if folder_id:
        try:
            folder = Folder.objects.get(id=folder_id, owner=request.user)
        except Folder.DoesNotExist:
            return JsonResponse({'error': 'Folder not found.'}, status=404)

    # Build breadcrumb trail
    breadcrumbs = [{'id': None, 'name': 'My Drive'}]
    if folder:
        chain = []
        node = folder
        while node:
            chain.append({'id': node.id, 'name': node.name})
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
                'icon_type': get_file_icon(mf.mime_type),
                'thumbnail_url': build_thumb_url(request, mf),
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


# --- SECURITY HARDENED SHARING ENDPOINTS ---

@login_required
@require_http_methods(["GET"])
def search_users(request):
    """
    API for authors to search accounts by username for sharing.
    Excludes the requesting user.
    """
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'users': []})

    from django.contrib.auth import get_user_model
    UserModel = get_user_model()

    matching_users = UserModel.objects.filter(
        username__icontains=q
    ).exclude(id=request.user.id).order_by('username')[:10]

    return JsonResponse({
        'users': [{'id': u.id, 'username': u.username} for u in matching_users]
    })


@login_required
@require_http_methods(["POST"])
def toggle_share_status(request):
    """
    Owner API to toggle public/shared access ON or OFF for a file or folder.
    Delegates to update_share_settings to maintain consistent state.
    """
    data = get_request_data(request)
    is_shared = bool(data.get('is_shared', False))
    data['share_mode'] = 'link' if is_shared else 'private'
    return update_share_settings(request, _custom_data=data)


@login_required
@require_http_methods(["POST"])
def update_share_settings(request, _custom_data=None):
    """
    Owner API to update share mode ('private', 'restricted', 'link')
    and set allowed recipient users.
    """
    data = _custom_data if _custom_data is not None else get_request_data(request)
    item_type = data.get('type')  # 'file' or 'folder'
    item_id = data.get('id')
    share_mode = data.get('share_mode', 'private')  # 'private', 'restricted', 'link'
    user_ids = data.get('user_ids', [])

    if item_type not in ('file', 'folder') or not item_id:
        return JsonResponse({'error': 'Invalid request parameters.'}, status=400)
    if share_mode not in ('private', 'restricted', 'link'):
        return JsonResponse({'error': 'Invalid share mode.'}, status=400)

    import uuid
    from django.contrib.auth import get_user_model
    UserModel = get_user_model()

    if item_type == 'folder':
        try:
            item = Folder.objects.get(id=item_id, owner=request.user)
        except Folder.DoesNotExist:
            return JsonResponse({'error': 'Folder not found.'}, status=404)
    else:
        try:
            item = MediaFile.objects.get(id=item_id, owner=request.user)
        except MediaFile.DoesNotExist:
            return JsonResponse({'error': 'File not found.'}, status=404)

    if not item.share_token:
        item.share_token = uuid.uuid4()

    item.share_mode = share_mode
    item.is_shared = (share_mode != 'private')
    item.save()

    if share_mode == 'restricted':
        valid_users = UserModel.objects.filter(id__in=user_ids).exclude(id=request.user.id)
        item.shared_users.set(valid_users)
    else:
        item.shared_users.clear()

    if item_type == 'folder':
        invalidate_user_folder_cache(request.user.id)

    share_token_str = str(item.share_token)
    share_url = request.build_absolute_uri(f'/share/{share_token_str}/')

    return JsonResponse({
        'success': True,
        'share_mode': item.share_mode,
        'is_shared': item.is_shared,
        'share_token': share_token_str,
        'share_url': share_url,
        'shared_users': [{'id': u.id, 'username': u.username} for u in item.shared_users.all()]
    })


@login_required
@require_http_methods(["GET"])
def get_share_status(request):
    """
    Owner API to fetch current share status, share mode, URL, & shared users for a file or folder.
    """
    item_type = request.GET.get('type')
    item_id = request.GET.get('id')

    if item_type == 'folder':
        try:
            item = Folder.objects.get(id=item_id, owner=request.user)
        except Folder.DoesNotExist:
            return JsonResponse({'error': 'Folder not found.'}, status=404)
    elif item_type == 'file':
        try:
            item = MediaFile.objects.get(id=item_id, owner=request.user)
        except MediaFile.DoesNotExist:
            return JsonResponse({'error': 'File not found.'}, status=404)
    else:
        return JsonResponse({'error': 'Invalid request parameters.'}, status=400)

    import uuid
    if not item.share_token:
        item.share_token = uuid.uuid4()
        item.save(update_fields=['share_token'])

    token_str = str(item.share_token)
    share_url = request.build_absolute_uri(f'/share/{token_str}/')

    return JsonResponse({
        'success': True,
        'share_mode': item.share_mode,
        'is_shared': item.is_shared,
        'share_token': token_str,
        'share_url': share_url,
        'item_name': item.name if item_type == 'folder' else item.filename,
        'shared_users': [{'id': u.id, 'username': u.username} for u in item.shared_users.all()]
    })


@login_required
def shared_item_view(request, share_token):
    """
    Renders recipient SPA page for a shared file or folder link.
    Requires authenticated user on NitroStream.
    """
    # 1. Check if token belongs to a Folder
    try:
        shared_folder = Folder.objects.get(share_token=share_token)
        if not shared_folder.is_shared or shared_folder.share_mode == 'private':
            return render(request, 'media_manager/shared_view.html', {
                'error': 'This shared item does not exist or access has been disabled by the author.',
            }, status=404)

        if not user_has_share_access_to_folder(request.user, shared_folder):
            return render(request, 'media_manager/shared_view.html', {
                'error': 'Access Denied: This item is restricted and has not been shared with your account.',
            }, status=403)

        return render(request, 'media_manager/shared_view.html', {
            'share_token': str(share_token),
            'item_type': 'folder',
            'shared_name': shared_folder.name,
            'owner_name': shared_folder.owner.username,
        })
    except Folder.DoesNotExist:
        pass

    # 2. Check if token belongs to a MediaFile
    try:
        shared_file = MediaFile.objects.get(share_token=share_token)
        if not shared_file.is_shared or shared_file.share_mode == 'private':
            return render(request, 'media_manager/shared_view.html', {
                'error': 'This shared item does not exist or access has been disabled by the author.',
            }, status=404)

        if not user_has_share_access_to_file(request.user, shared_file):
            return render(request, 'media_manager/shared_view.html', {
                'error': 'Access Denied: This item is restricted and has not been shared with your account.',
            }, status=403)

        return render(request, 'media_manager/shared_view.html', {
            'share_token': str(share_token),
            'item_type': 'file',
            'shared_name': shared_file.filename,
            'owner_name': shared_file.owner.username,
        })
    except MediaFile.DoesNotExist:
        pass

    # Active share not found
    return render(request, 'media_manager/shared_view.html', {
        'error': 'This shared item does not exist or access has been disabled by the author.',
    }, status=404)


@login_required
@require_http_methods(["GET"])
def get_shared_contents(request, share_token, subfolder_id=None):
    """
    API for recipients to fetch contents of a shared folder or subfolders within the shared subtree.
    STRICT SECURITY MEASURE: Validates tree boundaries and account permissions.
    """
    # 1. If share_token is a single MediaFile
    try:
        shared_file = MediaFile.objects.get(share_token=share_token)
        if not shared_file.is_shared or shared_file.share_mode == 'private':
            return JsonResponse({'error': 'Share link expired or invalid.'}, status=404)

        if not user_has_share_access_to_file(request.user, shared_file):
            return JsonResponse({'error': 'Access Denied: This item is not shared with your account.'}, status=403)

        return JsonResponse({
            'success': True,
            'item_type': 'file',
            'shared_root': {'name': shared_file.filename, 'owner': shared_file.owner.username},
            'breadcrumbs': [{'id': None, 'name': shared_file.filename}],
            'folders': [],
            'files': [{
                'id': shared_file.id,
                'filename': shared_file.filename,
                'file_size': shared_file.file_size,
                'mime_type': shared_file.mime_type,
                'icon_type': get_file_icon(shared_file.mime_type),
                'thumbnail_url': build_thumb_url(request, shared_file),
                'stream_url': f'/stream/{shared_file.id}/',
                'created_at': shared_file.created_at.isoformat(),
            }]
        })
    except MediaFile.DoesNotExist:
        pass

    # 2. Check if share_token is a shared Folder
    try:
        shared_root = Folder.objects.get(share_token=share_token)
        if not shared_root.is_shared or shared_root.share_mode == 'private':
            return JsonResponse({'error': 'Share link expired or invalid.'}, status=404)

        if not user_has_share_access_to_folder(request.user, shared_root):
            return JsonResponse({'error': 'Access Denied: This item is not shared with your account.'}, status=403)
    except Folder.DoesNotExist:
        return JsonResponse({'error': 'Share link expired or invalid.'}, status=404)

    target_folder = shared_root
    if subfolder_id is not None:
        try:
            target_folder = Folder.objects.get(id=subfolder_id)
        except Folder.DoesNotExist:
            return JsonResponse({'error': 'Subfolder not found.'}, status=404)

        # STRICT SECURITY BOUNDARY CHECK: Target folder MUST be a descendant of shared_root
        if not is_descendant_of(target_folder, shared_root):
            return JsonResponse({'error': 'Access denied: outside shared directory scope.'}, status=403)

    # Build breadcrumb chain starting at shared_root (hiding parent folders above shared_root!)
    chain = []
    node = target_folder
    while node:
        chain.append({'id': node.id, 'name': node.name})
        if node.id == shared_root.id:
            break
        node = node.parent
    breadcrumbs = list(reversed(chain))

    subfolders = Folder.objects.filter(parent=target_folder).annotate(file_count=Count('files')).order_by('name')
    files = MediaFile.objects.filter(folder=target_folder).order_by('-created_at')

    return JsonResponse({
        'success': True,
        'item_type': 'folder',
        'shared_root': {'name': shared_root.name, 'owner': shared_root.owner.username},
        'breadcrumbs': breadcrumbs,
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
                'icon_type': get_file_icon(mf.mime_type),
                'thumbnail_url': build_thumb_url(request, mf),
                'stream_url': f'/stream/{mf.id}/',
                'created_at': mf.created_at.isoformat(),
            }
            for mf in files
        ],
    })
