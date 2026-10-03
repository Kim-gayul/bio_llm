import uuid
from django.db import models


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_key = models.CharField(max_length=40, db_index=True)
    title = models.CharField(max_length=100, default="새 연구 대화")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10)
    content = models.TextField(blank=True)
    sources = models.JSONField(default=list)
    status = models.CharField(max_length=12, default="complete")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
