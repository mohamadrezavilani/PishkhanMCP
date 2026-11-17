import uuid

from django.db import models


class Visitor(models.Model):
    """A browser-owned pilot workspace, not an identity derived from an input UUID."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.OneToOneField("core.AccountSession", null=True, on_delete=models.PROTECT)
    active_turn = models.CharField(max_length=36, blank=True)
    otp_sent_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ChatTurn(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE)
    client_key = models.UUIDField()
    fingerprint = models.CharField(max_length=64)
    state = models.CharField(max_length=16, default="running")
    response = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["visitor", "client_key"], name="portal_turn_key")]


class PaymentSnapshot(models.Model):
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE)
    payment_key = models.CharField(max_length=256)
    data = models.JSONField(default=dict)
    observed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["visitor", "payment_key"], name="portal_payment_key")]


class Feedback(models.Model):
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField()
    comment = models.CharField(max_length=2000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
