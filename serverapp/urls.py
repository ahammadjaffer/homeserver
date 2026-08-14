from django.urls import path
from . import views

urlpatterns = [
    # Legacy flat-file endpoints (kept for backward compat, no longer on root)
    path('legacy/gallery/', views.list_images, name='legacy_gallery'),
    path('legacy/delete/', views.delete_file, name='delete_file'),
    path('upload-ajax/', views.upload_single_file, name='upload_single_file'),
]