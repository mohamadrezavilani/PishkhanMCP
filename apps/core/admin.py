from django.contrib import admin

from .models import AccountSession, Conversation, Operation, Quote, SavedItem


@admin.register(AccountSession)
class AccountSessionAdmin(admin.ModelAdmin):
    list_display = ["id", "mode", "phone", "state", "updated_at"]
    exclude = ["token", "device_session"]


@admin.register(Operation)
class OperationAdmin(admin.ModelAdmin):
    list_display = ["id", "service_id", "action_id", "status", "created_at"]
    list_filter = ["status", "service_id"]
    readonly_fields = ["id", "request_hash", "idempotency_key", "result"]


admin.site.register([Quote, SavedItem, Conversation])
