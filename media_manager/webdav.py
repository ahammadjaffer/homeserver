"""
NitroStream WebDAV Interface (RFC 4918)
Enables mounting NitroStream as a native desktop network drive (Windows Explorer, macOS Finder, Linux)
with HTTP Basic Authentication, full CRUD, locking, and delta sync with the Django database.
"""

import os
import re
import uuid
import base64
import mimetypes
import urllib.parse
from datetime import datetime, timezone
from email.utils import formatdate

from django.http import HttpResponse, StreamingHttpResponse, FileResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate
from django.conf import settings
from django.db.models import Sum
from django.core.files.base import ContentFile

from .models import Folder, MediaFile
from .signals import invalidate_user_folder_cache
from .tasks import generate_image_thumbnail, generate_video_preview


class WebDAVHandler:
    """
    Handles WebDAV requests for an authenticated user.
    """

    def __init__(self, request, path=""):
        self.request = request
        self.raw_path = path or ""
        # Normalize path: remove leading/trailing slashes and decode URL percent-encoding
        clean_path = urllib.parse.unquote(self.raw_path).strip('/')
        self.path_segments = [p for p in clean_path.split('/') if p and p != '.']
        self.user = None

    def authenticate_user(self):
        """
        Extracts HTTP Basic Auth credentials and verifies with Django User model.
        """
        auth_header = self.request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Basic '):
            return None

        try:
            encoded_creds = auth_header.split(' ', 1)[1].strip()
            decoded_creds = base64.b64decode(encoded_creds).decode('utf-8')
            username, password = decoded_creds.split(':', 1)
            user = authenticate(self.request, username=username, password=password)
            if user and user.is_active:
                return user
        except Exception:
            return None
        return None

    def require_auth(self):
        """Returns standard 401 Unauthorized response requesting Basic Auth."""
        response = HttpResponse("Unauthorized. Please provide NitroStream credentials.\n", status=401)
        response['WWW-Authenticate'] = 'Basic realm="NitroStream WebDAV"'
        return response

    def dispatch(self):
        """Main entrypoint for all WebDAV HTTP methods."""
        # OPTIONS request can be served directly without auth (RFC 4918 requirement for WebDAV discovery)
        if self.request.method.upper() == 'OPTIONS':
            return self.handle_options()

        # Check authentication (or if user already authenticated via Django session)
        if hasattr(self.request, 'user') and self.request.user and self.request.user.is_authenticated:
            self.user = self.request.user
        else:
            self.user = self.authenticate_user()

        if not self.user:
            return self.require_auth()

        method = self.request.method.upper()
        handler_name = f"handle_{method.lower()}"
        handler = getattr(self, handler_name, None)

        if handler:
            try:
                return handler()
            except Exception as e:
                return HttpResponse(f"Internal WebDAV Error: {str(e)}\n", status=500)

        # Default response for unsupported method
        res = HttpResponse("Method Not Allowed\n", status=405)
        res['Allow'] = "OPTIONS, GET, HEAD, PROPFIND, PUT, DELETE, MKCOL, MOVE, COPY, PROPPATCH, LOCK, UNLOCK"
        return res

    # ─── PATH RESOLUTION HELPERS ─────────────────────────────────────────────

    def resolve_target(self, segments=None):
        """
        Resolves path segments to (folder_obj, file_obj, parent_folder_obj, is_root).
        """
        if segments is None:
            segments = self.path_segments

        if not segments:
            return (None, None, None, True)  # Root collection

        current_folder = None
        # Walk down folder hierarchy
        for i, segment in enumerate(segments):
            is_last = (i == len(segments) - 1)

            # Try finding subfolder matching segment name
            subfolder = Folder.objects.filter(
                owner=self.user,
                parent=current_folder,
                name=segment
            ).first()

            if subfolder:
                if is_last:
                    return (subfolder, None, current_folder, False)
                current_folder = subfolder
                continue

            # If not a folder and it's the last segment, check if it's a file
            if is_last:
                media_file = MediaFile.objects.filter(
                    owner=self.user,
                    folder=current_folder,
                    filename=segment
                ).first()
                if media_file:
                    return (None, media_file, current_folder, False)

            # Segment not found
            return (None, None, current_folder, False)

        return (None, None, current_folder, False)

    # ─── WEBDAV METHOD HANDLERS ──────────────────────────────────────────────

    def handle_options(self):
        """Handles OPTIONS request — returns WebDAV protocol compliance."""
        response = HttpResponse("", status=200)
        response['DAV'] = '1, 2'
        response['MS-Author-Via'] = 'DAV'
        response['Allow'] = 'OPTIONS, GET, HEAD, PROPFIND, PUT, DELETE, MKCOL, MOVE, COPY, PROPPATCH, LOCK, UNLOCK'
        response['Accept-Ranges'] = 'bytes'
        response['Content-Length'] = '0'
        return response

    def handle_propfind(self):
        """Handles PROPFIND request — returns XML multistatus of resource and children."""
        depth = self.request.META.get('HTTP_DEPTH', '1').strip().lower()
        if depth not in ('0', '1', 'infinity'):
            depth = '1'

        folder, media_file, parent, is_root = self.resolve_target()

        # Check if requested item exists
        if not is_root and folder is None and media_file is None:
            return HttpResponse("Resource not found\n", status=404)

        base_webdav_prefix = "/webdav"
        xml_responses = []

        def build_folder_response(href_path, display_name, created_dt):
            rfc_date = formatdate(created_dt.timestamp(), usegmt=True) if created_dt else formatdate(usegmt=True)
            iso_date = created_dt.strftime('%Y-%m-%dT%H:%M:%SZ') if created_dt else datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            encoded_href = urllib.parse.quote(href_path, safe='/:@&=+$,')
            return f"""<D:response>
    <D:href>{encoded_href}</D:href>
    <D:propstat>
        <D:prop>
            <D:displayname>{self._xml_escape(display_name)}</D:displayname>
            <D:resourcetype><D:collection/></D:resourcetype>
            <D:getlastmodified>{rfc_date}</D:getlastmodified>
            <D:creationdate>{iso_date}</D:creationdate>
            <D:supportedlock>
                <D:lockentry>
                    <D:lockscope><D:exclusive/></D:lockscope>
                    <D:locktype><D:write/></D:locktype>
                </D:lockentry>
            </D:supportedlock>
        </D:prop>
        <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
</D:response>"""

        def build_file_response(href_path, mf):
            rfc_date = formatdate(mf.created_at.timestamp(), usegmt=True)
            iso_date = mf.created_at.strftime('%Y-%m-%dT%H:%M:%SZ')
            etag = f'"{mf.id}-{int(mf.created_at.timestamp())}"'
            mime = mf.mime_type or mimetypes.guess_type(mf.filename)[0] or 'application/octet-stream'
            encoded_href = urllib.parse.quote(href_path, safe='/:@&=+$,')
            return f"""<D:response>
    <D:href>{encoded_href}</D:href>
    <D:propstat>
        <D:prop>
            <D:displayname>{self._xml_escape(mf.filename)}</D:displayname>
            <D:getcontentlength>{mf.file_size}</D:getcontentlength>
            <D:getcontenttype>{mime}</D:getcontenttype>
            <D:getetag>{etag}</D:getetag>
            <D:resourcetype/>
            <D:getlastmodified>{rfc_date}</D:getlastmodified>
            <D:creationdate>{iso_date}</D:creationdate>
            <D:supportedlock>
                <D:lockentry>
                    <D:lockscope><D:exclusive/></D:lockscope>
                    <D:locktype><D:write/></D:locktype>
                </D:lockentry>
            </D:supportedlock>
        </D:prop>
        <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
</D:response>"""

        # 1. Self item
        if is_root:
            curr_href = f"{base_webdav_prefix}/"
            xml_responses.append(build_folder_response(curr_href, "My Drive", datetime.now(timezone.utc)))
        elif folder:
            rel_folder_path = "/".join(self.path_segments)
            curr_href = f"{base_webdav_prefix}/{rel_folder_path}/"
            xml_responses.append(build_folder_response(curr_href, folder.name, folder.created_at))
        elif media_file:
            rel_file_path = "/".join(self.path_segments)
            curr_href = f"{base_webdav_prefix}/{rel_file_path}"
            xml_responses.append(build_file_response(curr_href, media_file))

        # 2. Children if depth != '0' and item is collection
        if depth != '0' and (is_root or folder):
            target_folder = folder  # None if is_root
            rel_prefix = "/".join(self.path_segments)
            path_base = f"{base_webdav_prefix}/{rel_prefix}/" if rel_prefix else f"{base_webdav_prefix}/"

            # Subfolders
            child_folders = Folder.objects.filter(owner=self.user, parent=target_folder).order_by('name')
            for cf in child_folders:
                child_href = f"{path_base}{cf.name}/"
                xml_responses.append(build_folder_response(child_href, cf.name, cf.created_at))

            # Files
            child_files = MediaFile.objects.filter(owner=self.user, folder=target_folder).order_by('filename')
            for cmf in child_files:
                child_href = f"{path_base}{cmf.filename}"
                xml_responses.append(build_file_response(child_href, cmf))

        xml_content = f"""<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:">
{chr(10).join(xml_responses)}
</D:multistatus>"""

        response = HttpResponse(xml_content, status=207, content_type='application/xml; charset="utf-8"')
        return response

    def handle_get(self):
        """Handles GET request — streams file contents or displays basic directory listing."""
        folder, media_file, parent, is_root = self.resolve_target()

        if is_root or folder:
            # Return basic HTML directory listing
            title = "My Drive" if is_root else folder.name
            return HttpResponse(f"<html><body><h1>NitroStream WebDAV: {self._xml_escape(title)}</h1></body></html>", content_type="text/html")

        if not media_file or not media_file.file:
            return HttpResponse("File not found\n", status=404)

        try:
            file_handle = media_file.file.open('rb')
            response = FileResponse(file_handle, content_type=media_file.mime_type or 'application/octet-stream')
            response['Content-Length'] = media_file.file_size
            response['Last-Modified'] = formatdate(media_file.created_at.timestamp(), usegmt=True)
            response['ETag'] = f'"{media_file.id}-{int(media_file.created_at.timestamp())}"'
            response['Accept-Ranges'] = 'bytes'
            return response
        except Exception:
            return HttpResponse("Error reading file stream\n", status=500)

    def handle_head(self):
        """Handles HEAD request — metadata headers without body."""
        folder, media_file, parent, is_root = self.resolve_target()
        if is_root or folder:
            return HttpResponse("", status=200, content_type="text/html")

        if not media_file:
            return HttpResponse("", status=404)

        response = HttpResponse("", status=200, content_type=media_file.mime_type or 'application/octet-stream')
        response['Content-Length'] = media_file.file_size
        response['Last-Modified'] = formatdate(media_file.created_at.timestamp(), usegmt=True)
        response['ETag'] = f'"{media_file.id}-{int(media_file.created_at.timestamp())}"'
        response['Accept-Ranges'] = 'bytes'
        return response

    def handle_put(self):
        """Handles PUT request — saves or updates file content and triggers delta processing."""
        if not self.path_segments:
            return HttpResponse("Cannot PUT to root collection\n", status=405)

        filename = self.path_segments[-1]
        folder_segments = self.path_segments[:-1]

        # Resolve parent folder
        if folder_segments:
            folder, _, _, _ = self.resolve_target(folder_segments)
            if not folder:
                return HttpResponse("Parent directory does not exist\n", status=409)
        else:
            folder = None  # Root folder

        # Read binary body payload
        payload = self.request.body
        new_size = len(payload)

        # Enforce quota
        used_bytes = MediaFile.objects.filter(owner=self.user).aggregate(s=Sum('file_size'))['s'] or 0
        quota_bytes = (self.user.storage_quota_mb or 5000) * 1048576

        # Check if existing file is being overwritten
        existing_file = MediaFile.objects.filter(owner=self.user, folder=folder, filename=filename).first()
        old_size = existing_file.file_size if existing_file else 0

        if (used_bytes - old_size + new_size) > quota_bytes:
            return HttpResponse("Storage quota exceeded\n", status=507)

        mime_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

        is_created = False
        if existing_file:
            # Overwrite file content
            existing_file.file.save(filename, ContentFile(payload), save=False)
            existing_file.file_size = new_size
            existing_file.mime_type = mime_type
            existing_file.save()
            media_file = existing_file
        else:
            media_file = MediaFile(
                owner=self.user,
                folder=folder,
                filename=filename,
                file_size=new_size,
                mime_type=mime_type
            )
            media_file.file.save(filename, ContentFile(payload), save=True)
            is_created = True

        # Dispatch async thumbnail and preview generators for media files
        if mime_type.startswith('image/'):
            try:
                generate_image_thumbnail(media_file.id)
            except Exception:
                pass
        elif mime_type.startswith('video/'):
            try:
                generate_video_preview(media_file.id)
            except Exception:
                pass

        invalidate_user_folder_cache(self.user.id)

        response = HttpResponse("", status=201 if is_created else 204)
        response['ETag'] = f'"{media_file.id}-{int(media_file.created_at.timestamp())}"'
        return response

    def handle_mkcol(self):
        """Handles MKCOL request — creates new directory/folder."""
        if not self.path_segments:
            return HttpResponse("Root collection already exists\n", status=405)

        folder_name = self.path_segments[-1]
        parent_segments = self.path_segments[:-1]

        # Resolve parent folder
        if parent_segments:
            parent_folder, _, _, _ = self.resolve_target(parent_segments)
            if not parent_folder:
                return HttpResponse("Parent directory does not exist\n", status=409)
        else:
            parent_folder = None

        # Check if folder already exists
        if Folder.objects.filter(owner=self.user, parent=parent_folder, name=folder_name).exists():
            return HttpResponse("Collection already exists\n", status=405)

        Folder.objects.create(
            owner=self.user,
            parent=parent_folder,
            name=folder_name
        )

        invalidate_user_folder_cache(self.user.id)
        return HttpResponse("", status=201)

    def handle_delete(self):
        """Handles DELETE request — removes file or folder and cleans disk assets."""
        folder, media_file, parent, is_root = self.resolve_target()

        if is_root:
            return HttpResponse("Cannot delete root collection\n", status=405)

        if not folder and not media_file:
            return HttpResponse("Resource not found\n", status=404)

        if media_file:
            self._delete_media_file(media_file)
        elif folder:
            self._delete_folder_recursive(folder)

        invalidate_user_folder_cache(self.user.id)
        return HttpResponse("", status=204)

    def _delete_media_file(self, mf):
        """Removes physical file, thumbnail, hover preview and DB record."""
        for field in [mf.file, mf.thumbnail, mf.hover_preview]:
            if field:
                try:
                    if os.path.exists(field.path):
                        os.remove(field.path)
                except Exception:
                    pass
        mf.delete()

    def _delete_folder_recursive(self, folder):
        """Recursively removes all files, previews, subfolders, and DB records."""
        for mf in folder.files.all():
            self._delete_media_file(mf)
        for sub in folder.subfolders.all():
            self._delete_folder_recursive(sub)
        folder.delete()

    def handle_move(self):
        """Handles MOVE request — renames or moves resource to new destination."""
        folder, media_file, parent, is_root = self.resolve_target()

        if is_root or (not folder and not media_file):
            return HttpResponse("Source resource not found\n", status=404)

        dest_header = self.request.META.get('HTTP_DESTINATION', '').strip()
        if not dest_header:
            return HttpResponse("Destination header required\n", status=400)

        # Parse destination URL / path
        parsed_dest = urllib.parse.urlparse(dest_header)
        dest_path = urllib.parse.unquote(parsed_dest.path)

        # Strip /webdav/ prefix
        webdav_prefix = "/webdav"
        if dest_path.startswith(webdav_prefix):
            dest_path = dest_path[len(webdav_prefix):]
        dest_segments = [p for p in dest_path.strip('/').split('/') if p and p != '.']

        if not dest_segments:
            return HttpResponse("Invalid destination\n", status=400)

        new_name = dest_segments[-1]
        dest_parent_segments = dest_segments[:-1]

        # Resolve destination parent folder
        if dest_parent_segments:
            dest_parent_folder, _, _, _ = self.resolve_target(dest_parent_segments)
            if not dest_parent_folder:
                return HttpResponse("Destination parent folder does not exist\n", status=409)
        else:
            dest_parent_folder = None

        overwrite = self.request.META.get('HTTP_OVERWRITE', 'T').upper() == 'T'

        if media_file:
            existing = MediaFile.objects.filter(owner=self.user, folder=dest_parent_folder, filename=new_name).first()
            if existing:
                if not overwrite:
                    return HttpResponse("Destination already exists\n", status=412)
                self._delete_media_file(existing)

            media_file.filename = new_name
            media_file.folder = dest_parent_folder
            media_file.mime_type = mimetypes.guess_type(new_name)[0] or media_file.mime_type
            media_file.save()
        elif folder:
            existing = Folder.objects.filter(owner=self.user, parent=dest_parent_folder, name=new_name).first()
            if existing:
                if not overwrite:
                    return HttpResponse("Destination already exists\n", status=412)
                self._delete_folder_recursive(existing)

            folder.name = new_name
            folder.parent = dest_parent_folder
            folder.save()

        invalidate_user_folder_cache(self.user.id)
        return HttpResponse("", status=201)

    def handle_copy(self):
        """Handles COPY request — copies file to destination."""
        folder, media_file, parent, is_root = self.resolve_target()

        if is_root or not media_file:
            return HttpResponse("Only file copying is supported\n", status=400)

        dest_header = self.request.META.get('HTTP_DESTINATION', '').strip()
        parsed_dest = urllib.parse.urlparse(dest_header)
        dest_path = urllib.parse.unquote(parsed_dest.path)

        webdav_prefix = "/webdav"
        if dest_path.startswith(webdav_prefix):
            dest_path = dest_path[len(webdav_prefix):]
        dest_segments = [p for p in dest_path.strip('/').split('/') if p and p != '.']

        if not dest_segments:
            return HttpResponse("Invalid destination\n", status=400)

        new_name = dest_segments[-1]
        dest_parent_segments = dest_segments[:-1]

        if dest_parent_segments:
            dest_parent_folder, _, _, _ = self.resolve_target(dest_parent_segments)
            if not dest_parent_folder:
                return HttpResponse("Destination parent folder does not exist\n", status=409)
        else:
            dest_parent_folder = None

        # Create duplicate file record
        try:
            with media_file.file.open('rb') as f:
                content = f.read()

            new_mf = MediaFile(
                owner=self.user,
                folder=dest_parent_folder,
                filename=new_name,
                file_size=media_file.file_size,
                mime_type=media_file.mime_type
            )
            new_mf.file.save(new_name, ContentFile(content), save=True)
            invalidate_user_folder_cache(self.user.id)
            return HttpResponse("", status=201)
        except Exception as e:
            return HttpResponse(f"Copy failed: {str(e)}\n", status=500)

    def handle_lock(self):
        """
        Handles LOCK request — generates compliant lock discovery response
        enabling Windows Explorer and MS Office desktop editing.
        """
        lock_token = f"urn:uuid:{uuid.uuid4()}"
        timeout = self.request.META.get('HTTP_TIMEOUT', 'Second-3600')
        rel_path = "/".join(self.path_segments)
        href = f"/webdav/{rel_path}" if rel_path else "/webdav/"

        xml_response = f"""<?xml version="1.0" encoding="utf-8"?>
<D:prop xmlns:D="DAV:">
    <D:lockdiscovery>
        <D:activelock>
            <D:locktype><D:write/></D:locktype>
            <D:lockscope><D:exclusive/></D:lockscope>
            <D:depth>infinity</D:depth>
            <D:owner><D:href>{self._xml_escape(self.user.username)}</D:href></D:owner>
            <D:timeout>{timeout}</D:timeout>
            <D:locktoken><D:href>{lock_token}</D:href></D:locktoken>
            <D:lockroot><D:href>{href}</D:href></D:lockroot>
        </D:activelock>
    </D:lockdiscovery>
</D:prop>"""

        response = HttpResponse(xml_response, status=200, content_type='application/xml; charset="utf-8"')
        response['Lock-Token'] = f"<{lock_token}>"
        return response

    def handle_unlock(self):
        """Handles UNLOCK request."""
        response = HttpResponse("", status=204)
        lock_token = self.request.META.get('HTTP_LOCK_TOKEN', '')
        if lock_token:
            response['Lock-Token'] = lock_token
        return response

    def handle_proppatch(self):
        """Handles PROPPATCH request — acknowledges property updates."""
        rel_path = "/".join(self.path_segments)
        href = f"/webdav/{rel_path}" if rel_path else "/webdav/"

        xml_response = f"""<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:">
    <D:response>
        <D:href>{href}</D:href>
        <D:propstat>
            <D:status>HTTP/1.1 200 OK</D:status>
        </D:propstat>
    </D:response>
</D:multistatus>"""
        return HttpResponse(xml_response, status=207, content_type='application/xml; charset="utf-8"')

    def _xml_escape(self, text):
        """Escapes XML special characters."""
        if text is None:
            return ""
        return (str(text)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&apos;"))


@csrf_exempt
def webdav_endpoint(request, path=""):
    """
    Main Django view endpoint for WebDAV requests.
    Exempt from CSRF since WebDAV uses HTTP Basic Auth headers.
    """
    handler = WebDAVHandler(request, path)
    return handler.dispatch()
