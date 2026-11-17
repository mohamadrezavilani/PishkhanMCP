from django.contrib import admin

from .models import ChatTurn, Feedback, Visitor

admin.site.register([Visitor, ChatTurn, Feedback])
