from django.db import models

class MediaItem(models.Model):
    title = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to='uploads/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    # Status tracking for background processing
    is_processed = models.BooleanField(default=False)
    processing_error = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.title or self.file.name