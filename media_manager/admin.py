from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Folder, MediaFile


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'storage_quota_mb', 'is_staff')
    fieldsets = UserAdmin.fieldsets + (
        ('Quota Settings', {'fields': ('storage_quota_mb',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Quota Settings', {'fields': ('storage_quota_mb',)}),
    )


@admin.register(Folder)
class FolderAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'parent', 'created_at')
    list_filter = ('owner', 'created_at')
    search_fields = ('name', 'owner__username')
    raw_id_fields = ('owner', 'parent')


@admin.register(MediaFile)
class MediaFileAdmin(admin.ModelAdmin):
    list_display = ('filename', 'owner', 'folder', 'file_size', 'mime_type', 'created_at')
    list_filter = ('mime_type', 'owner', 'created_at')
    search_fields = ('filename', 'owner__username', 'mime_type')
    raw_id_fields = ('owner', 'folder')
