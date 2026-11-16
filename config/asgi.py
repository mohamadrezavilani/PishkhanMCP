import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django_application = get_asgi_application()

from apps.mcpserver.server import build_mcp_app  # noqa: E402

application = build_mcp_app(django_application)
