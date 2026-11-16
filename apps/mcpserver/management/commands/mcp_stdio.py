import asyncio

from django.core.management.base import BaseCommand

from apps.mcpserver.server import serve_stdio


class Command(BaseCommand):
    help = "Serve Pishkhan tools over MCP stdio for a local MCP client."
    # stdout belongs exclusively to the MCP protocol. Check/migrate explicitly
    # during setup instead of printing system-check diagnostics into the wire.
    requires_system_checks = []

    def handle(self, *args, **options):
        asyncio.run(serve_stdio())
