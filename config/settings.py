import json
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def flag(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "local-development-only-pishkhan-mcp")
DEBUG = flag("DJANGO_DEBUG", True)
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
CSRF_TRUSTED_ORIGINS = [x for x in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if x]
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.catalog",
    "apps.providers",
    "apps.agent",
    "apps.mcpserver",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

if os.getenv("DB_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": os.environ["DB_HOST"],
            "PORT": os.getenv("DB_PORT", "5432"),
            "NAME": os.getenv("DB_NAME", "pishkhan"),
            "USER": os.getenv("DB_USER", "pishkhan"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "CONN_MAX_AGE": 0,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {"timeout": 30},
        }
    }

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = "fa-ir"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

P24_MODE = os.getenv("P24_MODE", "demo").lower()
if P24_MODE not in {"demo", "live"}:
    raise ValueError("P24_MODE must be demo or live")
P24_API_BASE_URL = os.getenv("P24_API_BASE_URL", "https://core.pishkhan24.ayantech.ir/webservices").rstrip(
    "/"
)
P24_API_TIMEOUT = float(os.getenv("P24_API_TIMEOUT", "30"))
P24_APPLICATION = os.getenv("P24_APPLICATION", "pishkhan24")
P24_ORIGIN = os.getenv("P24_ORIGIN", "web")
P24_PLATFORM = os.getenv("P24_PLATFORM", "web")
P24_VERSION = os.getenv("P24_VERSION", "1.0.0")
P24_ACCESS_KEY = os.getenv("P24_ACCESS_KEY", "")
P24_DEVICE_PARAMETERS = json.loads(os.getenv("P24_DEVICE_PARAMETERS", "{}"))
P24_PAYMENT_CALLBACK = os.getenv("P24_PAYMENT_CALLBACK", "")
MCP_ALLOWED_HOSTS = [
    x for x in os.getenv("MCP_ALLOWED_HOSTS", "localhost:*,127.0.0.1:*,testserver").split(",") if x
]
AGENT_BASE_URL = os.getenv("AGENT_BASE_URL", "").rstrip("/")
AGENT_API_KEY = os.getenv("AGENT_API_KEY", "")
AGENT_MODEL = os.getenv("AGENT_MODEL", "")
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "12"))
AGENT_TIMEOUT = float(os.getenv("AGENT_TIMEOUT", "90"))
AGENT_PROXY_URL = os.getenv("AGENT_PROXY_URL", "").strip()
AGENT_WORKSPACE_ID = os.getenv("AGENT_WORKSPACE_ID", "").strip()
AGENT_DAILY_MESSAGE_LIMIT = int(os.getenv("AGENT_DAILY_MESSAGE_LIMIT", "10"))
