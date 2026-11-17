"""LAN mode hides development interfaces by peer address, never X-Forwarded-For.

Run the LAN launcher with --no-proxy-headers. This is not a reverse-proxy or
Internet deployment policy. Browser portal endpoints have independent ownership.
"""

from ipaddress import ip_address

from starlette.responses import JSONResponse


class LANBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            private = (
                path.rstrip("/") in {"/mcp", "/console"}
                or path.startswith("/admin")
                or (path.startswith("/api/") and not path.startswith("/api/portal/"))
            )
            peer = (scope.get("client") or ("", 0))[0]
            try:
                address = ip_address(peer)
                local = address.is_loopback or bool(
                    getattr(address, "ipv4_mapped", None) and address.ipv4_mapped.is_loopback
                )
            except ValueError:
                local = False
            if private and not local:
                await JSONResponse(
                    {
                        "ok": False,
                        "error": {"code": "PILOT_PORTAL_ONLY", "message": "Use the pilot home page."},
                    },
                    status_code=403,
                )(scope, receive, send)
                return
        await self.app(scope, receive, send)
