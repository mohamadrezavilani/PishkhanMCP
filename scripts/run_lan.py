"""Small trusted-LAN pilot: python scripts/run_lan.py --ip 192.168.1.20.

Use the project's virtualenv interpreter. Credentials stay in the local .env.
No firewall changes or router forwarding are performed by this launcher.
"""

import argparse
import ipaddress
import os
import secrets
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def candidate_ips():
    result = set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            value = ipaddress.ip_address(item[4][0])
            if value.is_private and not value.is_loopback and not value.is_link_local:
                result.add(str(value))
    except OSError:
        pass
    return sorted(result)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", help="LAN IPv4 of THIS computer, not 0.0.0.0 or your router")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--demo", action="store_true", help="Force synthetic Core/demo mode")
    parser.add_argument(
        "--check-only", action="store_true", help="Migrate/check and print URLs without serving"
    )
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    candidates = candidate_ips()
    ip = args.ip or (candidates[0] if len(candidates) == 1 else None)
    if not ip:
        parser.error("Choose --ip from ipconfig (candidates: " + ", ".join(candidates) + ")")
    try:
        address = ipaddress.IPv4Address(ip)
    except ValueError:
        parser.error("--ip must be an IPv4 address")
    if address.is_unspecified or address.is_loopback or address.is_multicast or not address.is_private:
        parser.error("--ip must be this computer's private LAN address, not 0.0.0.0")
    os.chdir(ROOT)
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    env = dict(os.environ)
    env.update(
        {
            "DJANGO_SETTINGS_MODULE": "config.settings",
            "P24_LAN_MODE": "true",
            "DJANGO_DEBUG": "false",
            "PYTHONUTF8": "1",
            "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1," + ip,
            "DJANGO_CSRF_TRUSTED_ORIGINS": f"http://localhost:{args.port},http://127.0.0.1:{args.port},http://{ip}:{args.port}",
        }
    )
    if args.demo:
        env["P24_MODE"] = "demo"
    if env.get("DJANGO_SECRET_KEY", "") in {
        "",
        "local-development-only-pishkhan-mcp",
        "replace-this-for-a-shared-installation",
    }:
        secret_file = ROOT / ".lan-secret"
        try:
            with secret_file.open("x", encoding="utf-8") as stream:
                stream.write(secrets.token_urlsafe(48))
        except FileExistsError:
            pass
        env["DJANGO_SECRET_KEY"] = secret_file.read_text(encoding="utf-8").strip()
        if not env["DJANGO_SECRET_KEY"]:
            parser.error(".lan-secret is empty; restore it or remove the empty file")
    print(f"Pilot page for colleagues: http://{ip}:{args.port}/", flush=True)
    print(f"Local developer console: http://127.0.0.1:{args.port}/console/", flush=True)
    print(
        "Mode: " + env.get("P24_MODE", "demo") + "; model budget unchanged; one worker; no proxy headers",
        flush=True,
    )
    print("Keep this terminal/computer running. Private/Domain firewall access may be required.", flush=True)
    for command in (["manage.py", "migrate", "--noinput"], ["manage.py", "check"]):
        subprocess.run([sys.executable, *command], env=env, cwd=ROOT, check=True)
    if args.check_only:
        return 0
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "config.asgi:application",
            "--host",
            "0.0.0.0",
            "--port",
            str(args.port),
            "--workers",
            "1",
            "--no-proxy-headers",
            "--limit-concurrency",
            "30",
        ],
        env=env,
        cwd=ROOT,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
    except KeyboardInterrupt:
        raise SystemExit(0) from None
