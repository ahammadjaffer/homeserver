from django.urls import path
from . import views

urlpatterns = [
    # Auth Routes
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Folder Management API Routes
    path('api/folders/create/', views.create_folder, name='api_create_folder'),
    path('api/folders/<int:folder_id>/rename/', views.rename_folder, name='api_rename_folder'),
    path('api/folders/<int:folder_id>/delete/', views.delete_folder, name='api_delete_folder'),
    path('api/folders/tree/', views.get_folder_tree, name='api_folder_tree'),
]
