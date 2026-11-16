# پوشش خدمات پیشخوان۲۴

این کاتالوگ از ۵۶ مدخل منوی عمومی [پیشخوان۲۴](https://pishkhan24.com/) در تاریخ ۲۰۲۶-۱۱-۱۶ تهیه شده است. هر ردیف یک مدخل محصول است و به معنی وجود یک API یا اجرای موفق آن نیست.

## معنای وضعیت‌ها

- `catalogued_requires_adapter`: خدمت قابل کشف است؛ اجرای واقعی به آداپتور و قرارداد تأییدشده نیاز دارد.
- `input_schema`: نام‌های نرمال‌شده برای ابزارهای ایجنت بر پایه فرم عمومی؛ بدنه درخواست تأمین‌کننده نیست.
- `requirements_status=unknown`: ورودی‌های معتبر هنوز استخراج نشده‌اند؛ به جای حدس زدن فیلد، آداپتور باید قرارداد واقعی بدهد.
- `requirements_status=ambiguous`: متن و فرم عمومی یکسان نیستند؛ مرجع نهایی قرارداد بک‌اند است.
- `cost_mode=unknown`: رایگان‌بودن نتیجه نمی‌شود؛ پیش از اجرای پولی باید تعرفه واقعی مشخص شود.
- `requires_account`: سیاست موقت اجرای محلی است و تأیید قرارداد احراز هویت upstream نیست؛ `account_requirement_verified` برای این snapshot برابر false است.
- وضعیت اجرای زنده را باید از provider فعال گرفت؛ شمارش ردیف‌های این فایل معیار تکمیل اتصال زنده نیست.

## جریان مشترک پیشنهادی

کشف خدمت ← دریافت نیازمندی‌ها از کاتالوگ و آداپتور ← اعلام هزینه واقعی ← اجرای درخواست ← پیگیری وضعیت ← نتیجه یا رسید.

خدمات دارای پرداخت، خرید یا تأیید هویت می‌توانند مراحل اختصاصی بیشتری داشته باشند. نام actionهای کاتالوگ توصیف قابلیت محصول است و به‌تنهایی یک API اجرایی ایجاد نمی‌کند.

## فهرست کامل

| شناسه پایدار | خدمت و منبع رسمی | گروه | هزینه استعلام/خرید | ورودی‌های مشاهده‌شده |
|---|---|---|---|---|
| `tamin` | [سوابق بیمه](https://pishkhan24.com/tamin/) | اجتماعی و بیمه | `paid` | شماره موبایل به نام شخص و ثبت‌شده در my.gov.ir |
| `electronicprescribe` | [نسخه تامین اجتماعی](https://pishkhan24.com/electronicprescribe/) | اجتماعی و بیمه | `unknown` | شماره موبایل و سال |
| `saham` | [ارزش سهام عدالت](https://pishkhan24.com/saham/) | اجتماعی و بیمه | `paid` | کد ملی؛ OTP در راهنما ذکر شده |
| `yaraneh` | [یارانه](https://pishkhan24.com/yaraneh/) | اجتماعی و بیمه | `unknown` | شماره موبایل سرپرست خانوار ثبت‌شده در gov.ir |
| `subsidy` | [دهک معیشتی](https://pishkhan24.com/subsidy/) | اجتماعی و بیمه | `paid` | فرم: موبایل و کد ملی سرپرست؛ متن: فقط موبایل + کد تایید؛ تعارض نیازمند قرارداد API |
| `electronic-subsidy` | [کالابرگ الکترونیکی](https://pishkhan24.com/electronic-subsidy/) | اجتماعی و بیمه | `unknown` | کد ملی و موبایل سرپرست + OTP؛ دو زیرخدمت استعلام و رمز خرید |
| `insurancepolicy` | [بیمه‌نامه](https://pishkhan24.com/insurancepolicy/) | اجتماعی و بیمه | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `fishmostamari` | [فیش تامین اجتماعی](https://pishkhan24.com/fishmostamari/) | اجتماعی و بیمه | `unknown` | موبایل به نام شخص ثبت‌شده در my.gov.ir |
| `fishekeshvari` | [فیش بازنشستگان کشوری](https://pishkhan24.com/fishekeshvari/) | اجتماعی و بیمه | `unknown` | کد ملی، شماره حساب، شماره دفتر کل، ماه و سال |
| `hokmmostamari` | [حکم تامین اجتماعی](https://pishkhan24.com/hokmmostamari/) | اجتماعی و بیمه | `unknown` | شماره موبایل و سال |
| `hokmbazneshasteghi` | [حکم بازنشستگان کشوری](https://pishkhan24.com/hokmbazneshasteghi/) | اجتماعی و بیمه | `unknown` | کد ملی، شماره حساب، شماره دفتر کل |
| `insurancecard` | [اعتبار دفترچه بیمه](https://pishkhan24.com/insurancecard/) | اجتماعی و بیمه | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `rentalcontractinquiry` | [اجاره نامه ملک](https://pishkhan24.com/rentalcontractinquiry/) | اجتماعی و بیمه | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `national-id-card` | [پیگیری کارت ملی](https://pishkhan24.com/national-id-card/) | اجتماعی و بیمه | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `my-simcart` | [سیم‌کارت‌های به‌نام](https://pishkhan24.com/my-simcart/) | اجتماعی و بیمه | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `study-exemption` | [معافیت تحصیلی](https://pishkhan24.com/study-exemption/) | اجتماعی و بیمه | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `exitban` | [استعلام ممنوع الخروجی](https://pishkhan24.com/exitban/) | اجتماعی و بیمه | `unknown` | کد ملی، موبایل، تاریخ تولد؛ نتیجه از طریق پیامک طبق صفحه |
| `exit-consent` | [رضایت خروج از کشور](https://pishkhan24.com/exit-consent/) | اجتماعی و بیمه | `unknown` | کد ملی، موبایل، تولد متقاضی؛ کد ملی و موبایل همسر/ولی؛ فقط استعلام رضایت موجود |
| `electricity` | [قبض برق](https://pishkhan24.com/electricity/) | قبض | `unknown` | شناسه قبض؛ یا شناسه قبض و پرداخت در خدمت قبض کاغذی |
| `water` | [قبض آب](https://pishkhan24.com/water/) | قبض | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `gas` | [قبض گاز](https://pishkhan24.com/gas/) | قبض | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `phone` | [قبض تلفن ثابت](https://pishkhan24.com/phone/) | قبض | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `mci` | [قبض همراه اول](https://pishkhan24.com/mci/) | قبض | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `irancell` | [قبض ایرانسل](https://pishkhan24.com/irancell/) | قبض | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `rightel` | [قبض رایتل](https://pishkhan24.com/rightel/) | قبض | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `avarezmelk` | [عوارض ملک](https://pishkhan24.com/avarezmelk/) | قبض | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `paperbill` | [قبض کاغذی](https://pishkhan24.com/paperbill/) | قبض | `unknown` | شناسه قبض و شناسه پرداخت |
| `taxipay` | [کرایه تاکسی](https://pishkhan24.com/taxipay/) | قبض | `paid` | تایپ یا اسکن بارکد؛ صفحه عمومی به نصب اپلیکیشن هدایت می‌کند |
| `khalafi` | [خلافی خودرو](https://pishkhan24.com/khalafi/) | خودرو و موتور | `paid` | پلاک؛ برای جزئیات کد ملی و موبایل مالک؛ تصاویر ممکن است هزینه جدا داشته باشند |
| `khalafimotor` | [خلافی موتورسیکلت](https://pishkhan24.com/khalafimotor/) | خودرو و موتور | `paid` | نامشخص؛ نیازمند قرارداد واقعی |
| `freeway` | [عوارض آزادراهی](https://pishkhan24.com/freeway/) | خودرو و موتور | `free` | پلاک: استعلام بدون جزئیات رایگان؛ جزئیات نیازمند اطلاعات مالک |
| `avarezkhodro` | [عوارض سالیانه خودرو](https://pishkhan24.com/avarezkhodro/) | خودرو و موتور | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `shahrdarikhodro` | [جریمه طرح ترافیک](https://pishkhan24.com/shahrdarikhodro/) | خودرو و موتور | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `nomremanfi` | [نمره منفی گواهینامه](https://pishkhan24.com/nomremanfi/) | خودرو و موتور | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `platenumber` | [پلاک‌های فعال](https://pishkhan24.com/platenumber/) | خودرو و موتور | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `bimesales` | [بیمه شخص ثالث](https://pishkhan24.com/bimesales/) | خودرو و موتور | `unknown` | جزئیات با کد یکتا+کد ملی؛ بدون جزئیات با پلاک فقط برای خودرو |
| `cartax` | [مالیات انتقال خودرو](https://pishkhan24.com/cartax/) | خودرو و موتور | `unknown` | پلاک و کد ملی مالک؛ فیلد تاریخ تولد در صفحه نیز وجود دارد |
| `motortransfertax` | [مالیات انتقال موتور](https://pishkhan24.com/motortransfertax/) | خودرو و موتور | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `technicalexaminationcertificate` | [معاینه فنی](https://pishkhan24.com/technicalexaminationcertificate/) | خودرو و موتور | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `cardocuments` | [کارت و سند خودرو](https://pishkhan24.com/cardocuments/) | خودرو و موتور | `paid` | نامشخص؛ نیازمند قرارداد واقعی |
| `drivinglicence` | [گواهینامه رانندگی](https://pishkhan24.com/drivinglicence/) | خودرو و موتور | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `carauthenticity` | [سوابق خودرو](https://pishkhan24.com/carauthenticity/) | خودرو و موتور | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `car-plate-history` | [تاریخچه پلاک](https://pishkhan24.com/car-plate-history/) | خودرو و موتور | `unknown` | پلاک، کد ملی و موبایل مالک؛ OTP در راهنمای رسمی |
| `topup` | [شارژ سیم کارت](https://pishkhan24.com/topup/) | شارژ و بسته | `paid` | موبایل، اپراتور با امکان تصحیح ترابرد، انتخاب محصول |
| `internetpackage` | [بسته اینترنت همراه](https://pishkhan24.com/internetpackage/) | شارژ و بسته | `paid` | موبایل، اپراتور با امکان تصحیح ترابرد، دائمی/اعتباری، بسته |
| `roaming` | [بسته‌های رومینگ](https://pishkhan24.com/roaming/) | شارژ و بسته | `paid` | نامشخص؛ نیازمند قرارداد واقعی |
| `sheba` | [دریافت شماره شبا](https://pishkhan24.com/sheba/) | بانکی و ارزی | `unknown` | شماره کارت/حساب/شبا، نوع حساب؛ تبدیل/استعلام |
| `sayad` | [چک صیادی](https://pishkhan24.com/sayad/) | بانکی و ارزی | `unknown` | شناسه صیاد؛ صفحه می‌گوید احراز هویت لازم نیست |
| `crypto` | [ارز دیجیتال](https://pishkhan24.com/crypto/) | بانکی و ارزی | `unknown` | فقط قیمت؛ خریدوفروش فراهم نیست |
| `bank-loans` | [استعلام تسهیلات بانکی](https://pishkhan24.com/bank-loans/) | بانکی و ارزی | `unknown` | شماره موبایل و کد ملی؛ پرداخت اقساط فراهم نیست |
| `posttracking` | [پیگیری مرسوله پستی](https://pishkhan24.com/posttracking/) | پستی | `paid` | کد رهگیری؛ هزینه استعلام؛ نتیجه شامل فرستنده/گیرنده و وضعیت |
| `passport` | [گذرنامه](https://pishkhan24.com/passport/) | پستی | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `postal-address-lookup` | [دریافت آدرس با کدپستی](https://pishkhan24.com/postal-address-lookup/) | پستی | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `military-card` | [کارت پایان خدمت](https://pishkhan24.com/military-card/) | پستی | `unknown` | نامشخص؛ نیازمند قرارداد واقعی |
| `transaction-check` | [اعتبار معاملاتی افراد](https://pishkhan24.com/transaction-check/) | قوه قضائیه | `unknown` | فرم کد ملی؛ متن کد ملی+موبایل؛ نیازمند رفع ابهام با API |
| `reputation-check` | [استعلام حسن شهرت](https://pishkhan24.com/reputation-check/) | قوه قضائیه | `unknown` | کد ملی و تاریخ تولد؛ پیگیری وضعیت بدون صدور گواهی |

## مرزهای مهم قابلیت‌ها

- `freeway`: رایگان‌بودن فقط به استعلام تجمیعی اشاره دارد. جزئیات تعرفه تأییدشده ندارد و پرداخت بدهی، عملیاتی پولی است.
- `posttracking`: استعلام پولی است؛ اثر مالی صرفاً به علت اطلاعاتی‌بودن خروجی حذف نمی‌شود.
- `crypto`: نمایش قیمت است؛ معامله ارز دیجیتال تعریف نشده است.
- `bank-loans`: استعلام تسهیلات است؛ پرداخت اقساط تعریف نشده است.
- `exit-consent`: استعلام رضایت موجود است؛ اعطای رضایت نیست.
- `reputation-check`: استعلام وضعیت است؛ صدور گواهی نیست.
- `taxipay`: صفحه عمومی مسیر اپلیکیشن را نشان می‌دهد؛ قابلیت وب باید مستقل تأیید شود.
- خدمات شارژ و بسته: اپراتور را از پیش‌شماره قطعی فرض نکنید؛ ترابرد وجود دارد.

## رابط Python

```python
from apps.catalog.catalog import catalog_page, get_service, list_services, service_requirements

list_services(category="postal")
catalog_page(query="قبض", limit=10)
get_service("posttracking")
service_requirements("electricity")
```

شناسه‌ها از آخرین بخش URL رسمی گرفته شده‌اند و با تغییر نام فارسی تغییر نمی‌کنند. جست‌وجو حروف عربی/فارسی و نیم‌فاصله را نرمال می‌کند. تابع‌ها کپی داده می‌دهند تا تغییر پاسخ یک درخواست، کاتالوگ درخواست دیگر را تغییر ندهد.
