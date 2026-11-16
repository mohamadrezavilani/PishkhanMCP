"""One tool registry shared by MCP, HTTP, the CLI, and the optional agent."""

from copy import deepcopy

from django.conf import settings
from jsonschema import Draft202012Validator

from apps.catalog.catalog import UnknownServiceError, catalog_page, list_categories, service_requirements
from apps.core import operations as ops
from apps.core.errors import PishkhanError
from apps.core.models import AccountSession, SavedItem
from apps.providers import demo
from apps.providers.client import redact
from apps.providers.registry import coverage, find_action, get_action, search_actions

_TOOLS = {}
S = {"type": "string", "minLength": 1}
SESSION = {**S, "description": "The current user's session_id from p24_create_session."}
KEY = {
    **S,
    "maxLength": 128,
    "description": "Stable unique key for this logical request; reuse only for the same input.",
}
OBJECT = {"type": "object"}


def tool(name, description, properties=None, required=(), *, read_only=False):
    def register(function):
        _TOOLS[name] = {
            "definition": {
                "name": name,
                "description": description,
                "inputSchema": {
                    "type": "object",
                    "properties": properties or {},
                    "required": list(required),
                    "additionalProperties": False,
                },
                "annotations": {
                    "readOnlyHint": read_only,
                    "destructiveHint": not read_only,
                    "openWorldHint": True,
                },
            },
            "handler": function,
        }
        return function

    return register


def list_tools():
    return [deepcopy(item["definition"]) for item in _TOOLS.values()]


def call_tool(name, arguments=None):
    entry = _TOOLS.get(name)
    if entry is None:
        return PishkhanError("UNKNOWN_TOOL", "ابزار شناخته نشد؛ فهرست ابزارها را دریافت کنید.").as_dict()
    arguments = arguments or {}
    invalid = next(Draft202012Validator(entry["definition"]["inputSchema"]).iter_errors(arguments), None)
    if invalid:
        return PishkhanError(
            "INVALID_ARGUMENTS",
            "ورودی ابزار معتبر نیست.",
            details={
                "field": ".".join(str(x) for x in invalid.absolute_path),
                "rule": invalid.validator,
                "required": entry["definition"]["inputSchema"]["required"],
            },
        ).as_dict()
    try:
        result = entry["handler"](**arguments)
        if not isinstance(result, dict):
            raise TypeError("Tool handlers must return objects")
        mode = settings.P24_MODE
        if arguments.get("session_id"):
            mode = (
                AccountSession.objects.filter(pk=arguments["session_id"])
                .values_list("mode", flat=True)
                .first()
                or mode
            )
        return {"ok": True, "mode": mode, **result}
    except PishkhanError as exc:
        return {"mode": settings.P24_MODE, **exc.as_dict()}
    except UnknownServiceError:
        return PishkhanError(
            "UNKNOWN_SERVICE", "خدمت شناخته نشد؛ ابتدا فهرست خدمات را دریافت کنید."
        ).as_dict()


@tool(
    "p24_capabilities",
    "وضعیت نصب، حالت demo/live و پوشش واقعی قراردادها؛ تعداد کاتالوگ به معنی آزمون زنده نیست.",
    read_only=True,
)
def capabilities():
    return {
        "mode": settings.P24_MODE,
        "catalog_service_count": sum(x["count"] for x in list_categories()),
        "demo_services": sorted(demo.DEMO_SERVICES),
        "provider": coverage(),
        "agent_configured": bool(settings.AGENT_BASE_URL and settings.AGENT_MODEL),
        "workflow": [
            "discover",
            "create_session",
            "login",
            "inspect_contract",
            "prepare_invoice",
            "resolve_prerequisites",
            "pay_if_required",
            "execute",
            "follow_status",
        ],
    }


@tool(
    "p24_list_services",
    "جست‌وجوی خدمات پیشخوان؛ نتیجهٔ کوتاه و صفحه‌بندی‌شده. برای ورودی‌ها p24_service_requirements را بگیرید.",
    {
        "query": {"type": "string"},
        "category": {"type": "string"},
        "offset": {"type": "integer", "minimum": 0},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    },
    read_only=True,
)
def services(query=None, category=None, offset=0, limit=20):
    page = catalog_page(category, query, offset=offset, limit=limit)
    short = []
    for item in page["items"]:
        record = {
            key: item[key]
            for key in ["id", "name_fa", "category", "category_fa", "description", "cost_mode", "source_url"]
        }
        record["observed_action_count"] = search_actions(service_id=item["id"], limit=1)["total"]
        record["demo_available"] = item["id"] in demo.DEMO_SERVICES
        short.append(record)
    return {**page, "items": short, "categories": list_categories()}


@tool(
    "p24_service_requirements",
    "شرح خدمت، ورودی‌های قابل مشاهده و عملیات واقعی مرتبط. فرم کاتالوگ با قرارداد API یکسان فرض نمی‌شود.",
    {"service_id": S},
    ["service_id"],
    read_only=True,
)
def requirements(service_id):
    return {
        **service_requirements(service_id),
        "actions": search_actions(service_id=service_id, limit=100),
        "recommended_flow": "p24_action_requirements -> p24_prepare_inquiry -> prerequisites/payment -> p24_run_inquiry",
    }


@tool(
    "p24_search_actions",
    "جست‌وجوی endpointهای مشاهده‌شده در خود پیشخوان؛ از query مانند wallet, history, login یا service_id استفاده کنید.",
    {
        "query": {"type": "string"},
        "service_id": {"type": "string"},
        "offset": {"type": "integer", "minimum": 0},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    },
    read_only=True,
)
def actions(query=None, service_id=None, offset=0, limit=20):
    return search_actions(query, service_id, offset, limit)


@tool(
    "p24_action_requirements",
    "قرارداد دقیق مشاهده‌شدهٔ یک action، فیلدها، اثر، منبع و میزان کامل‌بودن schema. فیلد ناشناخته را حدس نزنید.",
    {"action_id": S},
    ["action_id"],
    read_only=True,
)
def action_requirements(action_id):
    return {
        "action": get_action(action_id),
        "warning": "Source-verified does not mean authenticated live-tested.",
    }


@tool(
    "p24_create_session", "ایجاد نشست کاربری مستقل در حالت پیکربندی‌شده؛ در live ثبت دستگاه نیز انجام می‌شود."
)
def create_session():
    return ops.create_session()


@tool(
    "p24_session_status",
    "وضعیت نشست فعلی، بدون نمایش توکن.",
    {"session_id": SESSION},
    ["session_id"],
    read_only=True,
)
def session_status(session_id):
    return ops.get_session(session_id).public_dict()


@tool(
    "p24_import_session",
    "اتصال نشست فعلی به توکن موجود حساب خود کاربر در پیشخوان؛ توکن در نتیجه بازگردانده نمی‌شود.",
    {"session_id": SESSION, "token": S},
    ["session_id", "token"],
)
def import_session(session_id, token):
    return ops.import_session(session_id, token)


@tool(
    "p24_request_otp",
    "درخواست کد ورود پیشخوان برای شمارهٔ کاربر؛ در demo پیامکی ارسال نمی‌شود و کد 123456 است.",
    {"session_id": SESSION, "phone": S, "idempotency_key": KEY},
    ["session_id", "phone", "idempotency_key"],
)
def request_otp(session_id, phone, idempotency_key):
    return ops.login(session_id, phone, idempotency_key=idempotency_key)


@tool(
    "p24_verify_otp",
    "ارسال کد دریافت‌شده برای تکمیل ورود همان نشست.",
    {"session_id": SESSION, "phone": S, "otp": S, "idempotency_key": KEY},
    ["session_id", "phone", "otp", "idempotency_key"],
)
def verify_otp(session_id, phone, otp, idempotency_key):
    return ops.login(session_id, phone, otp=otp, idempotency_key=idempotency_key)


@tool(
    "p24_login_password",
    "ورود با نام کاربری/شماره و رمز کاربر؛ تبدیل مورد انتظار وب‌سایت در سرور انجام می‌شود.",
    {"session_id": SESSION, "phone": S, "password": S, "idempotency_key": KEY},
    ["session_id", "phone", "password", "idempotency_key"],
)
def login_password(session_id, phone, password, idempotency_key):
    return ops.login(session_id, phone, password=password, idempotency_key=idempotency_key)


@tool(
    "p24_close_session",
    "بستن نشست این برنامه و حذف توکن محلی؛ به معنی لغو تمام نشست‌های پیشخوان نیست.",
    {"session_id": SESSION},
    ["session_id"],
)
def close_session(session_id):
    session = ops.get_session(session_id)
    session.state, session.token, session.device_session = "closed", "", ""
    session.save()
    return {"session_id": str(session.pk), "state": "closed", "upstream_revocation": "not_attempted"}


@tool(
    "p24_execute_action",
    "اجرای یک action ثبت‌شده با فیلدهای واقعی قرارداد. ابتدا schema را بخوانید؛ این ابزار ممکن است هزینه/تغییر ایجاد کند. فقط live.",
    {"session_id": SESSION, "action_id": S, "parameters": OBJECT, "idempotency_key": KEY},
    ["session_id", "action_id", "parameters", "idempotency_key"],
)
def execute_action(session_id, action_id, parameters, idempotency_key):
    return ops.execute_action(session_id, action_id, parameters, idempotency_key)


@tool(
    "p24_prepare_inquiry",
    "ایجاد صورتحساب واقعی یک استعلام و دریافت PurchaseKey، پیش‌نیازها و کانال‌های پرداخت؛ خودش پرداخت نمی‌کند.",
    {"session_id": SESSION, "action_id": S, "parameters": OBJECT, "service_name": S, "idempotency_key": KEY},
    ["session_id", "action_id", "parameters", "idempotency_key"],
)
def prepare_inquiry(session_id, action_id, parameters, idempotency_key, service_name=None):
    return ops.prepare_inquiry(session_id, action_id, parameters, idempotency_key, service_name)


@tool(
    "p24_resume_inquiry",
    "ادامهٔ صورتحساب پس از ورود OTP مورد نیاز خدمت یا پذیرش پیام ConfigService؛ ورودی قبلی و ارتباط با همان خدمت حفظ می‌شود.",
    {
        "session_id": SESSION,
        "quote_id": S,
        "otp": S,
        "acknowledge_message": {"type": "boolean"},
        "idempotency_key": KEY,
    },
    ["session_id", "quote_id", "idempotency_key"],
)
def resume_inquiry(session_id, quote_id, idempotency_key, otp=None, acknowledge_message=False):
    return ops.resume_inquiry(
        session_id, quote_id, idempotency_key, otp=otp, acknowledge_message=acknowledge_message
    )


@tool(
    "p24_pay_quote",
    "پرداخت هزینهٔ صورتحساب با کانال انتخابی کاربر. درگاه redirect می‌دهد؛ انتخاب کیف پول می‌تواند اعتبار را کسر کند.",
    {
        "session_id": SESSION,
        "quote_id": S,
        "gateway": S,
        "use_credit": {"type": "boolean"},
        "idempotency_key": KEY,
    },
    ["session_id", "quote_id", "gateway", "use_credit", "idempotency_key"],
)
def pay_quote(session_id, quote_id, gateway, use_credit, idempotency_key):
    return ops.pay_quote(session_id, quote_id, gateway, use_credit, idempotency_key)


@tool(
    "p24_invoice_status",
    "بازخوانی وضعیت معتبر صورتحساب از پیشخوان؛ بازگشت از درگاه به‌تنهایی نشانهٔ موفقیت نیست.",
    {"session_id": SESSION, "quote_id": S},
    ["session_id", "quote_id"],
    read_only=True,
)
def invoice_status(session_id, quote_id):
    return ops.invoice_status(session_id, quote_id)


@tool(
    "p24_run_inquiry",
    "اجرای استعلام آماده‌شده با PurchaseKey همان صورتحساب؛ پس از تکمیل OTP/پرداخت لازم اجرا کنید.",
    {"session_id": SESSION, "quote_id": S, "idempotency_key": KEY},
    ["session_id", "quote_id", "idempotency_key"],
)
def run_inquiry(session_id, quote_id, idempotency_key):
    return ops.run_inquiry(session_id, quote_id, idempotency_key)


@tool(
    "p24_retry_inquiry",
    "تلاش صریح برای دریافت نتیجهٔ همان PurchaseKey پس از رفع رد قطعی قبلی (مثلاً تکمیل پرداخت). درخواست unknown/running/completed دوباره اجرا نمی‌شود و پرداخت جدید ایجاد نمی‌شود.",
    {"session_id": SESSION, "quote_id": S, "idempotency_key": KEY},
    ["session_id", "quote_id", "idempotency_key"],
)
def retry_inquiry(session_id, quote_id, idempotency_key):
    return ops.run_inquiry(session_id, quote_id, idempotency_key, retry_failed=True)


@tool(
    "p24_toll_summary",
    "عوارض تجمیعی آزادراه: در demo نتیجهٔ ساختگی، در live صورتحساب/پیش‌نیاز واقعی می‌دهد و سپس p24_run_inquiry لازم است.",
    {"session_id": SESSION, "plate": S, "idempotency_key": KEY},
    ["session_id", "plate", "idempotency_key"],
)
def toll_summary(session_id, plate, idempotency_key):
    return ops.simple_inquiry(session_id, "freeway", {"plate": ops.digits(plate)}, idempotency_key)


@tool(
    "p24_electricity_bill",
    "قبض برق: در demo قبض ساختگی، در live صورتحساب استعلام می‌دهد؛ با quote_id مراحل را ادامه دهید.",
    {"session_id": SESSION, "bill_id": S, "idempotency_key": KEY},
    ["session_id", "bill_id", "idempotency_key"],
)
def electricity_bill(session_id, bill_id, idempotency_key):
    return ops.simple_inquiry(session_id, "electricity", {"bill_id": ops.digits(bill_id)}, idempotency_key)


@tool(
    "p24_quote_parcel_inquiry",
    "دریافت هزینه و پیش‌نیاز استعلام مرسوله قبل از اجرا.",
    {"session_id": SESSION, "tracking_code": S, "idempotency_key": KEY},
    ["session_id", "tracking_code", "idempotency_key"],
)
def quote_parcel(session_id, tracking_code, idempotency_key):
    return ops.quote_parcel(session_id, tracking_code, idempotency_key)


@tool(
    "p24_run_parcel_inquiry",
    "اجرای استعلام مرسوله با quote_id قبلی؛ تکرار یک quote برداشت/اجرای محلی دوباره ایجاد نمی‌کند.",
    {"session_id": SESSION, "quote_id": S, "idempotency_key": KEY},
    ["session_id", "quote_id", "idempotency_key"],
)
def run_parcel(session_id, quote_id, idempotency_key):
    session = ops.get_session(session_id)
    quote = ops.get_quote(session, quote_id)
    if quote.service_id != "posttracking":
        raise PishkhanError("QUOTE_SERVICE_MISMATCH", "این پیشنهاد مربوط به مرسوله نیست.")
    return ops.run_inquiry(session_id, quote_id, idempotency_key)


@tool(
    "p24_prepare_bill_payment",
    "ساخت پرداخت قبض با UniqueIDهای برگشتی از استعلام. برای live کانال درگاه باید از پاسخ پیشخوان انتخاب شود.",
    {
        "session_id": SESSION,
        "bill_ids": {"type": "array", "items": S, "minItems": 1},
        "gateway": S,
        "idempotency_key": KEY,
    },
    ["session_id", "bill_ids", "gateway", "idempotency_key"],
)
def prepare_bill_payment(session_id, bill_ids, gateway, idempotency_key):
    session = ops.get_session(session_id)

    def perform():
        if session.mode == "demo":
            return {
                "demo": True,
                "bill_ids": bill_ids,
                "requires_user_action": True,
                "notice": "پرداخت نمایشی آماده شده؛ پولی جابه‌جا نشده است.",
                "next_step": "p24_demo_complete_payment",
            }
        if not settings.P24_PAYMENT_CALLBACK:
            raise PishkhanError("CALLBACK_NOT_CONFIGURED", "P24_PAYMENT_CALLBACK را تنظیم کنید.")
        result = ops.live_call(
            session,
            find_action("BillsPayment", "core"),
            {"Callback": settings.P24_PAYMENT_CALLBACK, "Gateway": gateway, "Bills": bill_ids},
        )
        if gateway.lower().startswith("wallet"):
            key = result.get("parameters", {}).get("PaymentKey")
            if not key:
                raise PishkhanError(
                    "PAYMENT_KEY_MISSING", "کلید پرداخت دریافت نشد.", details={"outcome": "unknown"}
                )
            result = ops.live_call(session, find_action("WalletPayment", "core"), {"PaymentKey": key})
        else:
            result["requires_user_action"] = bool(result.get("parameters", {}).get("RedirectLink"))
        return result

    return ops.execute_once(
        session,
        "bill_payment",
        {"Bills": bill_ids, "Gateway": gateway},
        idempotency_key,
        perform,
        service_id="electricity",
    )


@tool(
    "p24_demo_complete_payment",
    "فقط demo: شبیه‌سازی پاسخ موفق پرداخت برای آزمون فرایند و رسید؛ هرگز در live اجرا نمی‌شود.",
    {"session_id": SESSION, "operation_id": S},
    ["session_id", "operation_id"],
)
def demo_complete_payment(session_id, operation_id):
    session = ops.get_session(session_id)
    if session.mode != "demo":
        raise PishkhanError("DEMO_ONLY", "این ابزار فقط برای آزمایش محلی است.")
    operation = ops.get_operation(session, operation_id)
    if operation.action_id != "bill_payment":
        raise PishkhanError("INVALID_PAYMENT_OPERATION", "عملیات پرداخت نمایشی انتخاب نشده است.")
    operation.status = "completed"
    operation.result = {
        "demo": True,
        "payment_status": "simulated_success",
        "receipt": {
            "reference": f"DEMO-{operation.pk}",
            "currency": "IRR",
            "real_money_moved": False,
            "notice": "رسید نمایشی؛ اعتبار بانکی ندارد.",
        },
    }
    operation.save()
    return operation.public_dict()


@tool(
    "p24_operation_status",
    "وضعیت ثبت‌شدهٔ یک عملیات؛ برای وضعیت زندهٔ صورتحساب p24_invoice_status را بگیرید.",
    {"session_id": SESSION, "operation_id": S},
    ["session_id", "operation_id"],
    read_only=True,
)
def operation_status(session_id, operation_id):
    return ops.get_operation(ops.get_session(session_id), operation_id).public_dict()


@tool(
    "p24_get_transaction",
    "جزئیات عملیات ثبت‌شده در همین نشست، بدون حدس‌زدن وضعیت پرداخت.",
    {"session_id": SESSION, "operation_id": S},
    ["session_id", "operation_id"],
    read_only=True,
)
def get_transaction(session_id, operation_id):
    return operation_status(session_id, operation_id)


@tool(
    "p24_get_receipt",
    "رسید برگشتی و ذخیره‌شدهٔ عملیات؛ اگر رسید رسمی هنوز دریافت نشده باشد صریحاً اعلام می‌کند.",
    {"session_id": SESSION, "operation_id": S},
    ["session_id", "operation_id"],
    read_only=True,
)
def get_receipt(session_id, operation_id):
    operation = ops.get_operation(ops.get_session(session_id), operation_id)
    parameters = operation.result.get("parameters", {})
    receipt = operation.result.get("receipt") or (
        parameters.get("Receipt") if isinstance(parameters, dict) else None
    )
    return {
        "operation_id": str(operation.pk),
        "status": operation.status,
        "receipt_available": bool(receipt),
        "receipt": receipt,
        "next_step": None
        if receipt
        else "Inspect the source-verified invoice/history actions for the provider receipt.",
    }


@tool(
    "p24_wallet_balance",
    "موجودی کیف پول. در live ابتدا بدون wallet_id فهرست کیف پول‌ها را بگیرید و شناسهٔ برگشتی را انتخاب کنید.",
    {"session_id": SESSION, "wallet_id": S},
    ["session_id"],
    read_only=True,
)
def wallet_balance(session_id, wallet_id=None):
    session = ops.get_session(session_id)
    if session.mode == "demo":
        return {
            "mode": "demo",
            "demo": True,
            "balance": 2500000,
            "currency": "IRR",
            "notice": "اعتبار ساختگی",
        }
    endpoint = "UserWalletBalance" if wallet_id else "UserWallets"
    wire = {"Wallet": wallet_id, "CreditBalance": True} if wallet_id else {}
    return {"upstream": redact(ops.live_call(session, find_action(endpoint, "core"), wire))}


@tool(
    "p24_list_saved_items",
    "موارد ذخیره‌شده در همین پروژه و نشست؛ برای سوابق اصلی پیشخوان از actionهای UserQuery استفاده کنید.",
    {"session_id": SESSION},
    ["session_id"],
    read_only=True,
)
def saved_items(session_id):
    session = ops.get_session(session_id)
    return {
        "scope": "local_project",
        "items": [
            {"id": str(item.pk), "label": item.label, "service_id": item.service_id, "data": item.data}
            for item in session.saved_items.order_by("created_at")[:100]
        ],
    }


@tool(
    "p24_save_item",
    "ذخیرهٔ محلی شناسه یا پلاک برای استفادهٔ بعدی در همین نشست.",
    {"session_id": SESSION, "service_id": S, "label": S, "data": OBJECT},
    ["session_id", "service_id", "label", "data"],
)
def save_item(session_id, service_id, label, data):
    session = ops.get_session(session_id)
    service_requirements(service_id)
    item = SavedItem.objects.create(session=session, service_id=service_id, label=label, data=redact(data))
    return {"item_id": str(item.pk), "scope": "local_project"}
