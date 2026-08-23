import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings


class User(AbstractUser):
    storage_quota_mb = models.BigIntegerField(default=5000, help_text="Storage quota in MB")

    def __str__(self):
        return self.username


class Folder(models.Model):
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='folders'
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subfolders'
    )
    SHARE_MODE_CHOICES = (
        ('private', 'Private'),
        ('restricted', 'Restricted'),
        ('link', 'Anyone with Link'),
    )

    share_mode = models.CharField(max_length=20, choices=SHARE_MODE_CHOICES, default='private')
    shared_users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='shared_folders')
    is_shared = models.BooleanField(default=False)
    share_token = models.UUIDField(default=uuid.uuid4, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.is_shared = (self.share_mode != 'private')
        super().save(*args, **kwargs)

    class Meta:
        unique_together = ('name', 'parent', 'owner')
        ordering = ['name']

    def __str__(self):
        if self.parent:
            return f"{self.parent}/{self.name}"
        return self.name


class MediaFile(models.Model):
    SHARE_MODE_CHOICES = (
        ('private', 'Private'),
        ('restricted', 'Restricted'),
        ('link', 'Anyone with Link'),
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='files'
    )
    folder = models.ForeignKey(
        Folder,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='files'
    )
    file = models.FileField(upload_to='uploads/%Y/%m/%d/')
    filename = models.CharField(max_length=255)
    file_size = models.BigIntegerField()
    mime_type = models.CharField(max_length=100)
    thumbnail = models.ImageField(upload_to='thumbnails/%Y/%m/%d/', null=True, blank=True)
    hover_preview = models.ImageField(upload_to='previews/%Y/%m/%d/', null=True, blank=True)
    share_mode = models.CharField(max_length=20, choices=SHARE_MODE_CHOICES, default='private')
    shared_users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='shared_files')
    is_shared = models.BooleanField(default=False)
    share_token = models.UUIDField(default=uuid.uuid4, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.is_shared = (self.share_mode != 'private')
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.filename

