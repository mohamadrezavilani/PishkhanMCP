# اتصال کلاینت‌های MCP

این پروژه از SDK رسمی Python با نسخهٔ تثبیت‌شدهٔ `mcp==2.3.0` استفاده می‌کند.
همان ابزارهای هستهٔ Django از دو مسیر در دسترس هستند: **Streamable HTTP** برای
اتصال راه دور و **stdio** برای کلاینت محلی. پاسخ هر ابزار هم دادهٔ ساختاریافته
دارد و هم یک نسخهٔ JSON متنی برای کلاینت‌های قدیمی‌تر.

## آماده‌سازی

از ریشهٔ مخزن، وابستگی‌ها و پایگاه داده را مطابق README آماده کنید. حالت پیش‌فرض
`P24_MODE=demo` است. در این حالت نتیجه‌ها نمایشی‌اند؛ این اتصال به‌تنهایی نشانهٔ
اتصال واقعی حساب یا تکمیل یک استعلام واقعی نیست. برای اجرای واقعی، تنظیمات
provider و حساب لازم است و پوشش فعال هر خدمت باید بررسی شود.

## HTTP برای ایجنت یا کلاینت راه دور

```bash
python -m uvicorn config.asgi:application --host 127.0.0.1 --port 8000
```

آدرس محلی MCP:

```text
http://127.0.0.1:8000/mcp
```

نشانی را دقیقاً با `/mcp` وارد کنید. `python manage.py runserver` مسیر معمول
Django را اجرا می‌کند و جای سرور ASGI بالا برای MCP را نمی‌گیرد. برنامهٔ ASGI
چرخهٔ شروع و توقف SDK را اجرا می‌کند و سایر مسیرها را به Django می‌سپارد.

برای اتصال یک کلاینت ابری، همین برنامه باید روی نشانی HTTPS قابل دسترس آن
کلاینت اجرا شود. نمونهٔ `https://your-host.example/mcp` فقط قالب نشانی است؛
این مخزن به‌خودی‌خود سرور عمومی مستقرشده ایجاد نمی‌کند.

نام میزبان را در `MCP_ALLOWED_HOSTS` اضافه کنید. برای نمونه، برای یک دامنهٔ
HTTPS با نام `mcp.example.com` همین نام را به فهرست اضافه کنید. اگر
`P24_ACCESS_KEY` تنظیم شده باشد، کلاینت HTTP باید هدر
`Authorization: Bearer <configured-key>` را ارسال کند. این کلید مشترک مربوط به
دسترسی به سرور توسعه است و با توکن ورود به حساب پیشخوان تفاوت دارد.

### نمونهٔ Cursor

در فایل پیکربندی MCP کلاینت:

```json
{
  "mcpServers": {
    "pishkhan": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

در صورت تنظیم کلید مشترک، بخش زیر را به همان مدخل `pishkhan` اضافه کنید و
متغیر محیطی را در دستگاه کلاینت تنظیم کنید:

```json
"headers": {"Authorization": "Bearer ${env:P24_ACCESS_KEY}"}
```

### ChatGPT و Claude

در محیطی که افزودن سرور سفارشی MCP فعال است، آدرس HTTPS سرور را به‌عنوان
اتصال سفارشی اضافه کنید. این نسخه احراز هویت OAuth برای خود اتصال MCP ندارد؛
ورود به حساب پیشخوان از ابزارهای حساب انجام می‌شود. کلاینت باید اتصال بدون
OAuth به یک MCP سفارشی را برای آن محیط بپذیرد؛ در صورت فعال‌بودن کلید مشترک،
امکان ارسال هدر دلخواه نیز لازم است. پذیرش اتصال یا انتشار عمومی
در فهرست یک میزبان از قابلیت‌های خود سرور مستقل است.

رابط و دسترسی لازم به حساب و سیاست‌های محیط سازمانی وابسته است. راهنمای رسمی:

- [اتصال MCP در ChatGPT](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt)
- [اتصال‌های سفارشی Claude](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)
- [پیکربندی MCP در Cursor](https://cursor.com/docs/mcp)

این راهنما، آزمون اتصال در حساب واقعی این کلاینت‌ها را ادعا نمی‌کند. آزمون‌های
مخزن، پروتکل HTTP و stdio را با SDK رسمی بررسی می‌کنند.

## stdio برای کلاینت محلی

```bash
python manage.py mcp_stdio
```

فرمان منتظر پیام پروتکل روی stdin می‌ماند و رابط تعاملی ترمینال نیست. کلاینت
باید فرایند را اجرا و مدیریت کند. نمونهٔ پیکربندی:

```json
{
  "mcpServers": {
    "pishkhan": {
      "type": "stdio",
      "command": "/absolute/path/PishkhanMCP/.venv/bin/python",
      "args": ["/absolute/path/PishkhanMCP/manage.py", "mcp_stdio"],
      "env": {"P24_MODE": "demo"}
    }
  }
}
```

در ویندوز، مسیر interpreter معمولاً `.venv\\Scripts\\python.exe` است. مسیرها را
با مسیر واقعی دستگاه جایگزین کنید. هیچ متن یا پیام آغازینی نباید قبل از اجرای
فرمان روی stdout چاپ شود؛ stdout مسیر پیام‌های MCP است.

## آزمون با کلاینت رسمی Python

پس از اجرای سرور HTTP:

```python
import asyncio
from mcp import Client


async def main():
    async with Client("http://127.0.0.1:8000/mcp") as client:
        tools = await client.list_tools()
        print([tool.name for tool in tools.tools])
        result = await client.call_tool("p24_list_services", {})
        print(result.structured_content)


asyncio.run(main())
```

## قرارداد اتصال

- ابزارها از `apps.core.tools` خوانده می‌شوند؛ transport منطق کسب‌وکار جداگانه ندارد.
- ورودی‌ها پیش از dispatch با JSON Schema ابزار بررسی می‌شوند.
- خطای ابزار با `isError: true` و یک شیء خطا برمی‌گردد.
- نتیجه‌های پردازش، نیازمند ورودی و نیازمند اقدام کاربر باید از وضعیت واقعی
  عملیات خوانده شوند؛ متن گفت‌وگو جای وضعیت عملیات نیست.
- منبع `pishkhan://guide` راهنمای کار و `pishkhan://tools` قرارداد ابزارها را ارائه می‌کند.
- prompt به نام `pishkhan_task` یک آرگومان `request` می‌پذیرد.
- SDK از پروتکل جدید `2026-07-28` و مسیر سازگاری `initialize` قدیمی پشتیبانی
  می‌کند. تست HTTP، مذاکره با `2025-11-25` و تست جدید، discovery نسخهٔ جدید را بررسی می‌کنند.

```bash
pytest tests/test_mcp_protocol.py
```

منابع فنی:

- [SDK رسمی MCP برای Python](https://github.com/modelcontextprotocol/python-sdk)
- [اجرای سرور و transportها](https://py.sdk.modelcontextprotocol.io/run/)
- [تغییرات SDK نسخهٔ ۲](https://py.sdk.modelcontextprotocol.io/migration/)
