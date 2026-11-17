from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="portal"),
    path("portal-assets/<str:name>", views.asset),
    path("api/portal/state/", views.bootstrap),
    path("api/portal/otp/send/", views.send_otp),
    path("api/portal/otp/verify/", views.verify_otp),
    path("api/portal/logout/", views.logout),
    path("api/portal/chat/", views.chat),
    path("api/portal/turns/<uuid:client_key>/", views.turn_status),
    path("api/portal/history/<uuid:conversation_id>/", views.history),
    path("api/portal/payment/", views.payment_action),
    path("api/portal/feedback/", views.feedback),
]
