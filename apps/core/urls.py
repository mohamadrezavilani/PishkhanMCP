from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("health/", views.health, name="health"),
    path("api/tools/", views.tools_list),
    path("api/tools/call/", views.tools_call),
    path("api/services/", views.service_list),
    path("api/actions/", views.action_list),
    path("api/operations/", views.operation_list),
    path("api/chat/", views.chat),
    path("payments/return/", views.payment_return),
]
