from django.urls import path, re_path
from . import views
from . import webdav

urlpatterns = [
    # Public Landing Page & Drive SPA Root
    path('', views.landing_view, name='landing'),
    path('drive/', views.drive_view, name='list_images'),

    # Auth Routes
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Folder Management API Routes
    path('api/folders/create/', views.create_folder, name='api_create_folder'),
    path('api/folders/<int:folder_id>/rename/', views.rename_folder, name='api_rename_folder'),
    path('api/folders/<int:folder_id>/delete/', views.delete_folder, name='api_delete_folder'),
    path('api/folders/tree/', views.get_folder_tree, name='api_folder_tree'),

    # Folder Contents API (core navigation)
    path('api/folders/contents/', views.get_folder_contents, name='api_folder_contents_root'),
    path('api/folders/<int:folder_id>/contents/', views.get_folder_contents, name='api_folder_contents'),

    # File Management API Routes
    path('api/files/upload/', views.upload_media_file, name='api_upload_file'),
    path('api/files/<int:file_id>/delete/', views.delete_media_file, name='api_delete_file'),
    path('api/files/<int:file_id>/rename/', views.rename_media_file, name='api_rename_file'),
    path('api/files/<int:file_id>/move/', views.move_media_file, name='api_move_file'),

    # Streaming & Hover Preview Routes
    path('stream/<int:file_id>/', views.stream_media, name='stream_media'),
    path('preview/<int:file_id>/', views.stream_preview, name='stream_preview'),

    # Share Feature Routes
    path('api/users/search/', views.search_users, name='api_search_users'),
    path('api/shares/toggle/', views.toggle_share_status, name='api_toggle_share'),
    path('api/shares/update/', views.update_share_settings, name='api_update_share'),
    path('api/shares/status/', views.get_share_status, name='api_share_status'),
    path('share/<uuid:share_token>/', views.shared_item_view, name='shared_item_view'),
    path('api/shared/<uuid:share_token>/contents/', views.get_shared_contents, name='api_shared_contents_root'),
    path('api/shared/<uuid:share_token>/contents/<int:subfolder_id>/', views.get_shared_contents, name='api_shared_contents_sub'),

    # Shared Drive (Shared With Me) Routes
    path('api/shared-with-me/users/', views.get_shared_drive_users, name='api_shared_drive_users'),
    path('api/shared-with-me/users/<int:user_id>/contents/', views.get_shared_drive_user_contents, name='api_shared_drive_user_contents'),
    path('api/shared-with-me/folders/<int:folder_id>/contents/', views.get_shared_drive_folder_contents, name='api_shared_drive_folder_contents'),

    # Native WebDAV Interface (Desktop Network Drive Mounting)
    re_path(r'^webdav/?(?P<path>.*)$', webdav.webdav_endpoint, name='webdav_endpoint'),
]

