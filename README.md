# PishkhanMCP — پیشخوان با Django و MCP

زیرساخت اجرایی برای استفاده از خدمات پیشخوان۲۴ از طریق **MCP، API و یک ایجنت
گفت‌وگویی**. پروژه با Django 5.2 LTS و SDK رسمی MCP ساخته شده است و حالت
نمایشی قابل اجرا، اتصال HTTP به قراردادهای مشاهده‌شدهٔ پیشخوان، مدیریت نشست،
OTP و رمز عبور، ثبت عملیات و یک حلقهٔ واقعی model/tool دارد.

## وضعیت واقعی نسخهٔ فعلی

| بخش | وضعیت |
|---|---|
| Django، دیتابیس، API و MCP روی HTTP/stdio | پیاده‌سازی‌شده و قابل اجرا |
| کاتالوگ خدمات | ۵۶ مدخل عمومی، همراه نیازمندی‌ها و لینک منبع |
| رجیستری عملیات پیشخوان | ۱۵۳ endpoint مشاهده‌شده در JavaScript عمومی؛ قرارداد ورودی بسیاری از آن‌ها جزئی است |
| مسیرهای نمونه | عوارض آزادراهی، قبض برق و رهگیری مرسوله در حالت demo |
| ایجنت داخلی | حلقهٔ واقعی انتخاب و اجرای ابزار؛ نیازمند مدل سازگار با Chat Completions |
| ورود واقعی | ابزارهای OTP و password پیاده‌سازی شده‌اند؛ به نشست معتبر دستگاه نیاز دارند |
| پوشش واقعی همهٔ خدمات | هنوز با حساب معتبر و قرارداد داخلی شرکت آزموده نشده است |

**این مخزن، اجرای سرتاسری همهٔ خدمات واقعی پیشخوان را ادعا نمی‌کند.** وجود یک
endpoint در کد عمومی، به معنی تکمیل قرارداد، آمادگی همهٔ پیش‌نیازها یا موفقیت
پرداخت نیست. جزئیات در [وضعیت خدمات](docs/service-coverage.md) و
[برنامهٔ اعتبارسنجی live](docs/live-validation.md) آمده است. نگاشت خدمت‌به‌خدمت
در [جدول پوشش قراردادها](docs/action-coverage.md) و نتیجهٔ آزمون این نسخه در
[گزارش بررسی](docs/verification.md) ثبت شده است.

در بررسی عمومی اولیه، درخواست `DeviceRegister` با چهار فیلد runtime عمومی
پاسخ `GR0002` گرفت و نشست upstream ایجاد نشد. بنابراین برای شروع واقعی،
پارامترهای معتبر bootstrap شرکت یا یک نشست فعال متعلق به کاربر لازم است.
این مانع در خروجی ابزار گزارش می‌شود؛ نتیجهٔ نمایشی به جای نتیجهٔ واقعی برنمی‌گردد.

## شروع سریع محلی

پیش‌نیاز: Python 3.12 یا 3.13. دستورات زیر برای shell سازگار با Bash هستند:

```bash
git clone https://github.com/mohamadrezavilani/PishkhanMCP.git
cd PishkhanMCP
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
cp .env.example .env
python manage.py migrate
python manage.py check
python manage.py demo
python -m uvicorn config.asgi:application --host 127.0.0.1 --port 8000
```

نشانی `http://127.0.0.1:8000/` را باز کنید. پنل فارسی، ساخت نشست، انتخاب و
اجرای ابزار، جست‌وجوی خدمات، پیگیری عملیات و گفت‌وگوی ایجنت را ارائه می‌کند.

در PowerShell، فعال‌سازی محیط با `.venv\Scripts\Activate.ps1` و کپی فایل با
`Copy-Item .env.example .env` انجام می‌شود. در حالت محلی، خالی بودن `DB_HOST`
باعث استفاده از SQLite می‌شود.

حالت پیش‌فرض `P24_MODE=demo` است. پیامک، برداشت کیف پول یا پرداخت واقعی در
demo اجرا نمی‌شود. کد OTP نمایشی **`123456`** است. هر نشست mode خودش را نگه
می‌دارد؛ بعد از تغییر تنظیمات به live، یک نشست جدید بسازید.

فرمان `demo` سناریوهای نمونه را از ابزارهای واقعی هسته اجرا می‌کند و به مدل
زبانی یا کلید API نیاز ندارد. اجرای ایجنت گفت‌وگویی به تنظیم مدل نیاز دارد.

## مسیرهای برنامه

| مسیر | کاربرد |
|---|---|
| `GET /` | پنل فارسی اجرای ابزار و گفت‌وگو |
| `GET /health/` | سلامت برنامه |
| `GET /api/tools/` | قرارداد ابزارها |
| `POST /api/tools/call/` | اجرای ابزار با `name` و `arguments` |
| `GET /api/services/` | کاتالوگ خدمات |
| `GET /api/actions/` | جست‌وجوی عملیات مشاهده‌شدهٔ پیشخوان |
| `POST /api/chat/` | اجرای یک نوبت ایجنت داخلی |
| `GET /api/operations/?session_id=...` | عملیات ثبت‌شدهٔ یک نشست |
| `/mcp` | endpoint استاندارد MCP، با Streamable HTTP |
| `GET /payments/return/` | صفحهٔ بازگشت؛ تأیید پرداخت انجام نمی‌دهد |
| `/admin/` | مدیریت Django، در صورت ساخت superuser |

نمونهٔ ساخت نشست از API:

```bash
curl http://127.0.0.1:8000/api/tools/call/ \
  -H 'Content-Type: application/json' \
  -d '{"name":"p24_create_session","arguments":{}}'
```

نمونهٔ کشف خدمات:

```bash
curl http://127.0.0.1:8000/api/tools/call/ \
  -H 'Content-Type: application/json' \
  -d '{"name":"p24_list_services","arguments":{"query":"قبض"}}'
```

نام و ورودی دقیق همهٔ ابزارها را از `/api/tools/` یا `tools/list` دریافت کنید.
شناسهٔ `session_id` را از پاسخ ساخت نشست بردارید؛ برای عملیات اجرایی، همان
`idempotency_key` را هنگام تکرار همان درخواست نگه دارید.

برای مدیریت داده‌ها:

```bash
python manage.py createsuperuser
```

در استقرار ASGI، فایل‌های static پنل مدیریت را با `collectstatic` آماده و از
وب‌سرور جلویی ارائه کنید. `runserver` برای توسعهٔ معمول Django مناسب است؛
endpoint MCP از برنامهٔ ASGI بالا سرو می‌شود.

## اتصال MCP

آدرس محلی:

```text
http://127.0.0.1:8000/mcp
```

فرمان محلی stdio:

```bash
python manage.py mcp_stdio
```

کلاینت stdio این فرمان را به‌عنوان subprocess اجرا می‌کند؛ این فرمان رابط
تعاملی ترمینال نیست. نمونه‌های Cursor، ChatGPT، Claude و کلاینت Python در
[راهنمای اتصال MCP](docs/mcp-clients.md) قرار دارند.

برای کلاینت ابری، نشانی HTTPS قابل دسترس آن کلاینت لازم است. این مخزن هنوز
یک آدرس عمومی مستقرشده ارائه نمی‌کند. نام میزبان واقعی را به
`DJANGO_ALLOWED_HOSTS` و `MCP_ALLOWED_HOSTS` اضافه کنید.

در این مرحله OAuth پیاده‌سازی نشده است. `P24_ACCESS_KEY` اختیاری است؛ اگر
تنظیم شود، درخواست‌های API/MCP باید هدر زیر را داشته باشند:

```text
Authorization: Bearer <configured-key>
```

## ایجنت گفت‌وگویی داخلی

برای استفاده از MCP در یک کلاینت دیگر، تنظیم مدل در این پروژه لازم نیست.
برای استفاده از ایجنت داخلی، یک endpoint سازگار با **Chat Completions و tool
calling** را در `.env` معرفی کنید:

```dotenv
AGENT_BASE_URL=https://your-model-provider.example/v1
AGENT_API_KEY=your-model-key
AGENT_MODEL=your-tool-capable-model
AGENT_MAX_STEPS=12
```

آدرس بالا نمونه است. برنامه به انتهای `AGENT_BASE_URL` مسیر
`/chat/completions` اضافه می‌کند. برای مدلی که کلید لازم ندارد، مقدار کلید
می‌تواند خالی باشد.

پس از ساخت نشست:

```bash
python manage.py agent --session SESSION_UUID "خدمات قبض برق را توضیح بده"
```

برای ادامهٔ گفت‌وگو، شناسهٔ برگشتی را استفاده کنید:

```bash
python manage.py agent --session SESSION_UUID --conversation CONVERSATION_UUID "مرحله بعد را انجام بده"
```

همین قابلیت از `/api/chat/` با `session_id`، `message` و در نوبت‌های بعد
`conversation_id` قابل استفاده است. پاسخ شامل متن، فهرست فراخوانی ابزارها و
دلیل پایان نوبت است. بدون تنظیم مدل، خطای `agent_not_configured` برمی‌گردد؛
پاسخ ساختگی جای مدل تولید نمی‌شود.

## اتصال واقعی به پیشخوان

۱. `P24_MODE=live` را تنظیم و فرایند برنامه را دوباره اجرا کنید.

۲. قرارداد bootstrap شرکت را در `P24_DEVICE_PARAMETERS` قرار دهید؛ این مقدار
یک شیء JSON است و روی فیلدهای runtime پیش‌فرض اعمال می‌شود. نام فیلدهای
نامعلوم را حدس نزنید. مقدارهای پیش‌فرض `.env.example` به‌تنهایی در بررسی
اولیه نشست معتبر ایجاد نکردند.

۳. با `p24_create_session` یک نشست جدید بسازید. اگر bootstrap نیاز به تنظیم
داشت، اطلاعات صحیح دستگاه را اصلاح کنید یا از `p24_import_session` با توکن
فعال حساب خودتان استفاده کنید. ورود توکن، موفقیت upstream را به‌تنهایی
تأیید نمی‌کند؛ اولین فراخوانی معتبر آن را بررسی می‌کند.

۴. پس از آماده‌شدن نشست دستگاه، `p24_request_otp` و `p24_verify_otp` یا
`p24_login_password` را اجرا کنید. مقادیر واقعی را در کد، فایل نمونه یا commit
قرار ندهید.

۵. از `p24_search_actions` و `p24_action_requirements` برای بررسی قرارداد
عملیات استفاده کنید. جریان استعلام می‌تواند به `InvoiceRegister`، پیش‌نیازها،
پرداخت و `PurchaseKey` نیاز داشته باشد. برای این کار ابزارهای
`p24_prepare_inquiry`، `p24_resume_inquiry`، `p24_pay_quote`، `p24_invoice_status` و `p24_run_inquiry`
وجود دارند.

اگر دریافت نتیجه، قبل از تکمیل پرداخت با رد قطعی مواجه شد، پس از رفع علت از
`p24_retry_inquiry` استفاده کنید. این ابزار همان خرید را پیگیری می‌کند؛ عملیات
نامشخص را خودکار تکرار نمی‌کند و پرداخت یا صورتحساب تازه‌ای نمی‌سازد.

۶. برای پرداخت، `P24_PAYMENT_CALLBACK` باید آدرس بازگشت معتبرِ قرارداد واقعی
شرکت باشد. این تنظیم، endpoint جعلی یا تأیید خودکار پرداخت ایجاد نمی‌کند.
وضعیت نهایی از پاسخ معتبر و ابزار پیگیری خوانده می‌شود.
صفحهٔ `/payments/return/` فقط کاربر را به پیگیری راهنمایی می‌کند؛ در صورت
پذیرش این callback توسط محیط upstream می‌توان URL کامل آن را تنظیم کرد.

جزئیات گام‌ها، نتایج مشاهده‌شده و ثبت شواهد آزمون در
[live-validation.md](docs/live-validation.md) آمده است.

## Docker و PostgreSQL

فایل `.env` را از نمونه بسازید. Compose یک PostgreSQL و یک فرایند Uvicorn
اجرا می‌کند. پایگاه داده روی volume نگه داشته می‌شود و migration مرحله‌ای
صریح است:

```bash
docker compose build app
docker compose up -d db
docker compose run --rm app python manage.py migrate --noinput
docker compose up -d app
docker compose ps
```

پورت پیش‌فرض روی `127.0.0.1:8000` منتشر می‌شود. `PORT` و `BIND_ADDRESS`
قابل تنظیم‌اند. در مسیر HTTPS، reverse proxy را به همین پورت متصل کنید.
کلاینت Claude برای اتصال ابری به HTTPS استاندارد نیاز دارد؛ جزئیات محیط
کلاینت را در راهنمای رسمی مرتبط بررسی کنید.

اجرای نمونه در کانتینر:

```bash
docker compose exec app python manage.py demo
docker compose exec app python manage.py createsuperuser
```

بعد از دریافت نسخهٔ جدید:

```bash
docker compose build app
docker compose run --rm app python manage.py migrate --noinput
docker compose up -d app
```

Dockerfile از `requirements.lock` استفاده می‌کند. فایل `.env` و دیتابیس محلی
وارد image نمی‌شوند. اجرای Docker به معنی آزموده‌شدن پرداخت واقعی یا آمادگی
همهٔ خدمات upstream نیست.

## بررسی و آزمون

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
```

CI همین کنترل‌ها را با Python 3.12 و 3.13 اجرا می‌کند. آزمون‌های transport
از SDK رسمی استفاده می‌کنند و HTTP، مذاکرهٔ پروتکل، stdio و فراخوانی واقعی
کاتالوگ را پوشش می‌دهند. موفقیت این تست‌ها جای آزمون حساب واقعی پیشخوان و
مدل واقعیِ انتخاب‌شده را نمی‌گیرد.

برای به‌روزرسانی آگاهانهٔ قفل وابستگی‌ها:

```bash
uv pip compile pyproject.toml --extra dev --extra postgres -o requirements.lock
```

## ساختار و اسناد

- `apps/catalog`: کاتالوگ محصول و نیازمندی‌های عمومی خدمات.
- `apps/providers`: رجیستری endpointها، انتقال HTTP و ارائه‌دهندهٔ نمایشی.
- `apps/core`: ابزارها، نشست، عملیات، پیشنهاد هزینه و API.
- `apps/mcpserver`: transportهای رسمی MCP، resourceها و prompt.
- `apps/agent`: حلقهٔ مدل و ابزار و ادامهٔ گفت‌وگو.
- [معماری و قراردادهای داخلی](docs/architecture.md)
- [فهرست خدمات و وضعیت پوشش](docs/service-coverage.md)
- [اتصال کلاینت‌های MCP](docs/mcp-clients.md)
- [اعتبارسنجی اتصال واقعی](docs/live-validation.md)
- [بررسی سورس شرکت و HAR](docs/source-and-har-review.md)
