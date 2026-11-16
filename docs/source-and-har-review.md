# بررسی سورس شرکت و HAR پیشخوان۲۴

تاریخ بررسی: 2026-11-16

فایل‌های ورودی:
- `core-main.zip`: سورس C# پروژه Core؛ 1,395 فایل C#.
- `pishkhan24.com.har`: 409 ورودی شبکه. این HAR حاوی اطلاعات حساس نشست و ورود است و عمداً به مخزن اضافه نشده؛ فقط نام عملیات، ترتیب، نام فیلدها و کدهای وضعیت گزارش شده‌اند.

## Host و ثبت دستگاه

HAR از این host استفاده می‌کند:

```
https://core.pishkhan24.ayantech.ir/webservices/
```

در `Core/Main/ProjectValues.cs` نیز همین host در `HostOriginsMap` ثبت شده و Origin برابر `web` مجاز است. مقدار پیشین `ayanco.com` در تنظیمات MCP اشتباه بود. در `.env.example` و fallback در `config/settings.py` به `ayantech.ir` اصلاح شد.

HAR درخواست موفق `core.svc/v2/DeviceRegister` را با چهار فیلد `Application`, `Origin`, `Platform`, `Version` و `Identity.Token` خالی ثبت کرده است. پاسخ دارای `Parameters.Session` و `Status.Code=G00000` است.

سورس C# در `DeviceRegisterCommand.cs` نشان می‌دهد host باید در `HostOriginsMap` وجود داشته باشد، Origin باید در لیست همان host باشد، Version باید parse شود و سپس handler نشست دستگاه را ایجاد می‌کند. این دقیقاً علت اختلاف تلاش قبلی است: host اشتباه بود، نه کمبود فیلد اضافی.

## ترتیب درخواست‌های HAR

در HAR تعداد 14 درخواست POST به API پیشخوان ثبت شده است. توالی مرتبط:

1. `core/v2/DeviceRegister`
2. `core/v1/ConfigBasic`
3. `core/v1/LoginByOTP` — درخواست OTP
4. `core/v1/LoginByOTP` — تأیید OTP
5. `core/v1/ConfigBasic`
6. `core/v1/ConfigSearch`
7. `core/v1/UserQuickAccessItems`
8. `core/v1/UserServicesRecentlyUsed`
9. `core/v1/UserBasketGetItemCount`
10. `core/v1/UserServiceQueries`
11. `core/v1/ConfigService`
12. `services/v1/InvoiceRegister`
13. `services/v1/ElectricBills`
14. `core/v1/UserBasketGetItemCount`

همهٔ پاسخ‌های این توالی HTTP 200 و `Status.Code=G00000` داشتند. این موفقیت، شاهد اجرای وب‌سایت است؛ نه بازپخش تازه توسط MCP. OTP، شماره حساب، session و cookie در مخزن یا سند درج نشده‌اند.

## قرارداد ورود

فایل‌های C#:
- `Core/Intermediate/Modules/User/Commands/Device/V2/DeviceRegisterCommand.cs`
- `Core/Intermediate/Modules/User/Commands/Device/V2/DeviceRegisterHandler.cs`
- `Core/Intermediate/Modules/User/Commands/Login/LoginByOTPCommand.cs`
- `Core/Intermediate/Modules/User/Commands/Login/LoginByOTPHandler.cs`

OTP با `Username` و `OTPCode=null` درخواست می‌شود و با همان Username و کد دریافتی تأیید می‌شود. Handler از `Session.Verify` برای تأیید همان نشست دستگاه استفاده می‌کند؛ لازم نیست در پاسخ OTP توکن جدیدی برگردد.

فرانت‌اند رمز عبور را به lowercase SHA-1 hex تبدیل می‌کند. ابزار اختصاصی MCP این تبدیل wire-level را انجام می‌دهد. این تبدیل صرفاً سازگاری با upstream است و روش ذخیره‌سازی امن رمز نیست.

## قبض برق

فایل‌های C#:
- `ElectricBillsCommand.cs` و `ElectricBillsModel.cs`
- `InvoiceRegisterCommand.cs` و `InvoiceRegisterModel.cs`

مدل قبض برق شامل `Identifier` و `PurchaseKey` است. اعتبارسنجی شناسه با `Helper.IsValidGlobalBill(..., BillTypeEnum.Electric)` انجام می‌شود و Invoice با PurchaseKey اعتبارسنجی می‌شود.

در HAR، `ConfigService` پیش از `InvoiceRegister` اجرا می‌شود. ورودی InvoiceRegister شامل `Service` و `Parameters` است؛ Parameters داخلی یک JSON string است. سپس endpoint نتیجه `ElectricBills` با `Identifier` و `PurchaseKey` فراخوانی می‌شود. موفقیت استعلام را نباید با پرداخت‌شدن قبض اشتباه گرفت؛ وضعیت قبض از پاسخ نتیجه خوانده می‌شود.

## کرایه تاکسی؛ دو endpoint جدید

سورس C# دو endpoint را نشان می‌دهد که در رجیستری قبلی MCP وجود نداشتند. هر دو به `taxipay` نگاشت شدند:

1. `services/v1/MunicipalityTaxiFaresBillsBarcodeInfo`
   - ورودی: `Barcode`
   - دقیقاً 10 رقم و شروع با `10`
   - خروجی: اطلاعات مالک/خودرو، مسیر و کرایه‌های پیشنهادی.
2. `services/v1/MunicipalityTaxiFaresBills`
   - ورودی: `Barcode`, `Amount`, `PurchaseKey`
   - مبلغ بیشتر از صفر و حداکثر 1,000,000
   - نیازمند اعتبارسنجی Invoice با PurchaseKey.

فایل‌های مدل، command و handler در مسیر
`Core/Intermediate/Modules/Services/Vehicle/Commands/MunicipalityTolls/`
هستند. این دو endpoint در رجیستری اضافه شدند؛ HAR ارسالی آن‌ها را اجرا نکرده است، بنابراین source-verified هستند نه HAR-tested.

## پرداخت

سورس و رجیستری شامل `InvoicePayment`, `BillsPayment`, `WalletPayment` و `InvoiceDiscounts` هستند. انتخاب gateway و کیف پول باید از پاسخ‌های جاری `PaymentChannels` و walletها انجام شود. HAR ارسالی شامل پرداخت درگاه یا callback نیست؛ پس این بخش نیازمند آزمون مستقل است.

## تغییرات اعمال‌شده

- اصلاح host پیش‌فرض API به `core.pishkhan24.ayantech.ir`.
- افزودن دو عملیات کرایه تاکسی؛ رجیستری از 153 به 155 عملیات افزایش می‌یابد.
- افزودن آزمون هم‌ترازی host و قراردادهای Taxi.
- ثبت این گزارش بدون ذخیرهٔ داده‌های حساس HAR.

## وضعیت شواهد

| قابلیت | شاهد | وضعیت |
|---|---|---|
| DeviceRegister v2 | HAR + سورس C# | HAR-observed success |
| OTP login | HAR + handler C# | HAR-observed success |
| ConfigService و InvoiceRegister | HAR + مدل‌های C# | HAR-observed success |
| ElectricBills | HAR + مدل C# | HAR-observed success |
| Taxi barcode/payment | مدل و handler C# | source-verified، نه HAR-tested |
| پرداخت درگاه | سورس و قرارداد frontend | نیازمند آزمون مستقل |
| تمام خدمات کاتالوگ | رجیستری و سورس | نیازمند آزمون خدمت‌به‌خدمت |

این سند بررسی آفلاین فایل‌های ارائه‌شده است؛ درخواست‌های HAR روی محیط عملیاتی بازپخش نشده‌اند و پرداخت واقعی انجام نشده است.
