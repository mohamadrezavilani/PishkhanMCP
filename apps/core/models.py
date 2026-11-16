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


class UserRequest(models.Model):
    """One user behavior in MCP; not a fabricated upstream RequestID."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(AccountSession, on_delete=models.PROTECT, related_name="requests")
    client_key = models.CharField(max_length=128)
    service_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["session", "client_key"], name="unique_user_request_key")
        ]

    def public_dict(self):
        return {
            "request_id": str(self.pk),
            "request_id_origin": "mcp",
            "session_id": str(self.session_id),
            "service_id": self.service_id,
            "created_at": self.created_at.isoformat(),
        }


class Operation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        RUNNING = "running"
        COMPLETED = "completed"
        FAILED = "failed"
        UNKNOWN = "unknown"
        REQUIRES_ACTION = "requires_user_action"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(AccountSession, on_delete=models.PROTECT, related_name="operations")
    request = models.ForeignKey(
        UserRequest, null=True, blank=True, on_delete=models.PROTECT, related_name="operations"
    )
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
            "request_id": str(self.request_id) if self.request_id else None,
            "request_id_origin": "mcp",
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
    request = models.ForeignKey(
        UserRequest, null=True, blank=True, on_delete=models.PROTECT, related_name="quotes"
    )
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


class ProviderCall(models.Model):
    """One transport attempt within a user request; no raw credentials/bodies."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(AccountSession, on_delete=models.PROTECT)
    request = models.ForeignKey(
        UserRequest, null=True, blank=True, on_delete=models.PROTECT, related_name="calls"
    )
    operation = models.ForeignKey(
        Operation, null=True, blank=True, on_delete=models.PROTECT, related_name="calls"
    )
    action_id = models.CharField(max_length=160)
    upstream_request_id = models.CharField(max_length=256, blank=True)
    status = models.CharField(max_length=40, default="running")
    upstream_code = models.CharField(max_length=40, blank=True)
    duration_ms = models.FloatField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def public_dict(self):
        return {
            "call_id": str(self.pk),
            "action_id": self.action_id,
            "status": self.status,
            "upstream_request_id": self.upstream_request_id or None,
            "upstream_code": self.upstream_code,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat(),
        }


class CorrelationEdge(models.Model):
    """An observed identifier relation, never a same-session/time inference."""

    request = models.ForeignKey(
        UserRequest, null=True, blank=True, on_delete=models.PROTECT, related_name="correlations"
    )
    session = models.ForeignKey(AccountSession, on_delete=models.PROTECT)
    call = models.ForeignKey(ProviderCall, on_delete=models.PROTECT, related_name="correlations")
    source_type = models.CharField(max_length=40)
    source_key = models.CharField(max_length=256)
    target_type = models.CharField(max_length=40)
    target_key = models.CharField(max_length=256)
    evidence = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def public_dict(self):
        return {
            "source": {"type": self.source_type, "key": self.source_key},
            "target": {"type": self.target_type, "key": self.target_key},
            "evidence": self.evidence,
            "call_id": str(self.call_id),
        }


class PaymentAttempt(models.Model):
    session = models.ForeignKey(AccountSession, on_delete=models.PROTECT)
    request = models.ForeignKey(
        UserRequest, null=True, blank=True, on_delete=models.PROTECT, related_name="payments"
    )
    operation = models.ForeignKey(Operation, null=True, blank=True, on_delete=models.PROTECT)
    payment_key = models.CharField(max_length=256)
    purchase_key = models.CharField(max_length=256, blank=True)
    bill_ids = models.JSONField(default=list)
    gateway = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=40, default="Unknown")
    bill_statuses = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["session", "payment_key"], name="unique_session_payment")
        ]

    def public_dict(self):
        return {
            "payment_key": self.payment_key,
            "purchase_key": self.purchase_key or None,
            "request_id": str(self.request_id) if self.request_id else None,
            "bill_ids": self.bill_ids,
            "gateway": self.gateway,
            "payment_status": self.status,
            "bill_statuses": self.bill_statuses,
            "settled": self.status == "Settle",
        }
