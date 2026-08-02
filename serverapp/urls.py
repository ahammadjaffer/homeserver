from django.urls import path
from . import views

urlpatterns = [
    path('', views.list_images, name='list_images'),
    path('delete/', views.delete_file, name='delete_file'),
    path('upload-ajax/', views.upload_single_file, name='upload_single_file'),
]