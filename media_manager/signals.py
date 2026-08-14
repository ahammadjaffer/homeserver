from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import Folder, MediaFile


def get_folder_cache_key(user_id):
    return f"folder_tree_user_{user_id}"


def invalidate_user_folder_cache(user_id):
    if user_id:
        cache.delete(get_folder_cache_key(user_id))


@receiver([post_save, post_delete], sender=Folder)
@receiver([post_save, post_delete], sender=MediaFile)
def handle_folder_or_file_change(sender, instance, **kwargs):
    if instance.owner_id:
        invalidate_user_folder_cache(instance.owner_id)
