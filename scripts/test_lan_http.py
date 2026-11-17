"""Isolated HTTP regression: five browsers, fake model, demo Core, disposable DB.

Never loads live credentials or modifies the installation's SQLite/PostgreSQL DB.
The child listens on loopback only and is stopped when this script finishes.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
APP = """
import os, json
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
from django.conf import settings
settings.DATABASES["default"]["NAME"] = os.environ["PILOT_TEST_DB"]
import django
django.setup()
from django.core.management import call_command
call_command("migrate", verbosity=0)
from apps.agent import runner
import httpx

def fake_response(request):
    payload = json.loads(request.content)
    if payload["messages"][-1]["role"] == "tool":
        reply = {"role": "assistant", "content": "Synthetic demo result; no real inquiry."}
    else:
        reply = {"role": "assistant", "content": None, "tool_calls": [{
            "id": "synthetic-test-call", "type": "function",
            "function": {"name": "p24_electricity_bill", "arguments": '{"bill_id":"000100"}'}}]}
    return httpx.Response(200, json={"choices": [{"message": reply}]})
runner._make_client = lambda: httpx.Client(transport=httpx.MockTransport(fake_response))
from config.asgi import application
"""


def main():
    with tempfile.TemporaryDirectory(prefix="pishkhan-http-test-") as folder:
        root = Path(folder)
        (root / "pilot_test_app.py").write_text(APP, encoding="utf-8")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        env = {
            **os.environ,
            "PYTHONPATH": str(root) + os.pathsep + str(ROOT),
            "PYTHONUTF8": "1",
            "PYTHON_DOTENV_DISABLED": "1",
            "DJANGO_SETTINGS_MODULE": "config.settings",
            "DJANGO_DEBUG": "false",
            "DJANGO_SECRET_KEY": "synthetic-http-test-secret",
            "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
            "DB_HOST": "",
            "PILOT_TEST_DB": str(root / "test.sqlite3"),
            "P24_MODE": "demo",
            "P24_LAN_MODE": "true",
            "P24_ACCESS_KEY": "",
            "AGENT_BASE_URL": "https://model.example/v1",
            "AGENT_MODEL": "synthetic-test-model",
            "AGENT_API_KEY": "",
            "AGENT_PROXY_URL": "",
            "AGENT_WORKSPACE_ID": "",
            "AGENT_DAILY_MESSAGE_LIMIT": "10",
            "AGENT_MAX_STEPS": "4",
        }
        with (root / "server.log").open("w+", encoding="utf-8") as log:
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "pilot_test_app:application",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-proxy-headers",
                ],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=log,
            )
            clients = []
            try:
                base = f"http://127.0.0.1:{port}"
                with httpx.Client(base_url=base, trust_env=False, timeout=1) as ping:
                    for _ in range(100):
                        if proc.poll() is not None:
                            raise RuntimeError("Test server exited during startup")
                        try:
                            if ping.get("/health/").status_code == 200:
                                break
                        except httpx.RequestError:
                            pass
                        time.sleep(0.1)
                    else:
                        raise RuntimeError("Test server startup timeout")
                clients = [httpx.Client(base_url=base, trust_env=False, timeout=30) for _ in range(5)]

                def post(client, path, payload):
                    return client.post(
                        path, json=payload, headers={"X-CSRFToken": client.cookies["csrftoken"]}
                    )

                def run(index):
                    client = clients[index]
                    assert client.get("/").status_code == 200
                    r = post(client, "/api/portal/otp/send/", {"phone": f"091200001{index:02d}"})
                    assert r.status_code == 200, ("send", r.status_code, r.text[:150])
                    r = post(client, "/api/portal/otp/verify/", {"otp": "123456"})
                    assert r.status_code == 200, ("verify", r.status_code, r.text[:150])
                    conversation = None
                    for _ in range(2):
                        r = post(
                            client,
                            "/api/portal/chat/",
                            {
                                "message": "Synthetic electricity test",
                                "conversation_id": conversation,
                                "client_key": str(uuid.uuid4()),
                            },
                        )
                        assert r.status_code == 200, ("chat", r.status_code, r.text[:150])
                        result = r.json()
                        assert result["ok"]
                        conversation = result["conversation_id"]
                    return conversation

                with ThreadPoolExecutor(max_workers=5) as pool:
                    conversations = list(pool.map(run, range(5)))
                assert len(set(conversations)) == 5
                for i, client in enumerate(clients):
                    state = client.get("/api/portal/state/").json()
                    assert state["usage"]["used"] == 10
                    assert [c["id"] for c in state["conversations"]] == [conversations[i]]
                    other = conversations[(i + 1) % 5]
                    assert client.get(f"/api/portal/history/{other}/").status_code == 404
                denied = post(
                    clients[0],
                    "/api/portal/chat/",
                    {
                        "message": "Eleventh turn must be blocked",
                        "client_key": str(uuid.uuid4()),
                    },
                ).json()
                assert denied["error"]["code"] == "agent_daily_limit"
                print(
                    json.dumps(
                        {
                            "ok": True,
                            "browsers": 5,
                            "chat_turns": 10,
                            "eleventh_turn_blocked": True,
                            "cross_browser_isolation": True,
                            "real_core_calls": 0,
                            "real_model_calls": 0,
                        }
                    )
                )
            except Exception:
                log.flush()
                print((root / "server.log").read_text(encoding="utf-8")[-12000:], file=sys.stderr)
                raise
            finally:
                for client in clients:
                    client.close()
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)


if __name__ == "__main__":
    main()
