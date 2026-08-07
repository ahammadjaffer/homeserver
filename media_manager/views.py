import json
import mimetypes
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Count
from django.core.cache import cache

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


# --- FILE UPLOAD API ---

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
    generate_image_thumbnail.delay(media_file.id)

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
