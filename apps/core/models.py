import uuid

from django.db import models


class AccountSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mode = models.CharField(max_length=10, default="demo")
    phone = models.CharField(max_length=32, blank=True)
    state = models.CharField(max_length=32, default="guest")
    token = models.TextField(blank=True)
    device_session = models.TextField(blank=True)
    context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def public_dict(self):
        return {
            "session_id": str(self.pk),
            "mode": self.mode,
            "state": self.state,
            "phone": self.phone,
            "created_at": self.created_at.isoformat(),
        }


class Operation(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running"
        COMPLETED = "completed"
        FAILED = "failed"
        UNKNOWN = "unknown"
        REQUIRES_ACTION = "requires_user_action"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(AccountSession, on_delete=models.PROTECT, related_name="operations")
    service_id = models.CharField(max_length=100, blank=True)
    action_id = models.CharField(max_length=120)
    idempotency_key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    request_data = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.RUNNING)
    upstream_reference = models.CharField(max_length=256, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["session", "idempotency_key"], name="unique_session_request_key")
        ]
        indexes = [models.Index(fields=["session", "status", "created_at"])]

    def public_dict(self):
        return {
            "operation_id": str(self.pk),
            "session_id": str(self.session_id),
            "service_id": self.service_id,
            "action_id": self.action_id,
            "status": self.status,
            "mode": self.session.mode,
            "result": self.result,
            "upstream_reference": self.upstream_reference,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class Quote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(AccountSession, on_delete=models.CASCADE)
    service_id = models.CharField(max_length=100)
    action_id = models.CharField(max_length=120)
    parameters = models.JSONField(default=dict)
    amount = models.BigIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=8, default="IRR")
    expires_at = models.DateTimeField()
    operation = models.OneToOneField(Operation, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)


class SavedItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(AccountSession, on_delete=models.CASCADE, related_name="saved_items")
    service_id = models.CharField(max_length=100)
    label = models.CharField(max_length=200)
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(AccountSession, on_delete=models.CASCADE)
    messages = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
