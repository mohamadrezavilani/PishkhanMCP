import hashlib
import json
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.errors import PishkhanError
from apps.core.models import AccountSession, Operation, Quote
from apps.core.tracing import current_request, ensure_request, operation_scope, trace_call
from apps.providers import demo
from apps.providers.client import PishkhanClient, password_digest, redact
from apps.providers.registry import find_action, get_action, registry, validate_parameters
from apps.providers.service_mapping import normalize_inputs, resolve_service

DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def digits(value):
    return str(value).translate(DIGITS).strip()


def get_session(session_id):
    try:
        session = AccountSession.objects.get(pk=session_id)
    except (AccountSession.DoesNotExist, ValidationError, ValueError) as exc:
        raise PishkhanError("SESSION_NOT_FOUND", "نشست پیدا نشد؛ ابتدا یک نشست ایجاد کنید.") from exc
    if session.state == "closed":
        raise PishkhanError("SESSION_CLOSED", "نشست بسته شده است؛ یک نشست تازه ایجاد کنید.")
    return session


def get_operation(session, operation_id):
    try:
        return Operation.objects.select_related("session").get(pk=operation_id, session=session)
    except (Operation.DoesNotExist, ValidationError, ValueError) as exc:
        raise PishkhanError("OPERATION_NOT_FOUND", "عملیات در این نشست پیدا نشد.") from exc


def get_quote(session, quote_id, *, allow_expired=False):
    try:
        quote = Quote.objects.get(pk=quote_id, session=session)
    except (Quote.DoesNotExist, ValidationError, ValueError) as exc:
        raise PishkhanError("QUOTE_NOT_FOUND", "پیشنهاد هزینه در این نشست پیدا نشد.") from exc
    if not allow_expired and quote.expires_at <= timezone.now() and not quote.operation_id:
        raise PishkhanError("QUOTE_EXPIRED", "پیشنهاد هزینه منقضی شده است؛ دوباره قیمت را دریافت کنید.")
    return quote


def execute_once(session, action_id, parameters, idempotency_key, executor, *, service_id="", request=None):
    if not idempotency_key or len(idempotency_key) > 128:
        raise PishkhanError("IDEMPOTENCY_KEY_REQUIRED", "یک idempotency_key ثابت برای این درخواست لازم است.")
    request = request or ensure_request(session, action_id + ":" + idempotency_key, service_id)
    raw = json.dumps({"action": action_id, "parameters": parameters}, sort_keys=True, ensure_ascii=False)
    fingerprint = hashlib.sha256(raw.encode()).hexdigest()
    # The record is committed before the external side effect. A process crash
    # leaves a visible running operation, never an invitation to blindly repeat.
    with transaction.atomic():
        operation, created = Operation.objects.get_or_create(
            session=session,
            idempotency_key=idempotency_key,
            defaults={
                "request": request,
                "action_id": action_id,
                "service_id": service_id,
                "request_hash": fingerprint,
                "request_data": redact(parameters),
            },
        )
    if not created:
        if current_request() and operation.request_id and operation.request_id != current_request().pk:
            raise PishkhanError("REQUEST_MISMATCH", "This idempotency key belongs to another request.")
        if operation.request_hash != fingerprint:
            raise PishkhanError("IDEMPOTENCY_CONFLICT", "این کلید قبلاً برای ورودی متفاوت استفاده شده است.")
        return _operation_response(operation, replayed=True)
    return _complete_operation(operation, executor)


def _operation_response(operation, *, replayed=False):
    answer = operation.public_dict()
    answer["ok"] = operation.status not in {Operation.Status.FAILED, Operation.Status.UNKNOWN}
    if replayed:
        answer["replayed"] = True
    return answer


def _complete_operation(operation, executor):
    """Settle an already committed operation reservation without losing its ID."""
    try:
        with operation_scope(operation):
            result = executor()
        operation.result = redact(result)
        operation.status = (
            Operation.Status.REQUIRES_ACTION
            if result.get("requires_user_action")
            else Operation.Status.PENDING
            if result.get("pending")
            else Operation.Status.COMPLETED
        )
    except PishkhanError as exc:
        operation.result = exc.as_dict()
        operation.status = (
            Operation.Status.UNKNOWN if exc.details.get("outcome") == "unknown" else Operation.Status.FAILED
        )
    except Exception:
        operation.result = {
            "ok": False,
            "error": {
                "code": "EXECUTION_INTERRUPTED",
                "message": "اجرای عملیات کامل نشد؛ قبل از تکرار وضعیت را بررسی کنید.",
            },
        }
        operation.status = Operation.Status.UNKNOWN
    operation.save(update_fields=["result", "status", "updated_at"])
    return _operation_response(operation)


def _update_account(session, action, parameters, response):
    endpoint = action["path"].split("/")[-1].lower()
    result = response.get("parameters", {})
    if isinstance(result, dict):
        token = result.get("Session") or result.get("Token")
        if isinstance(token, str) and token:
            session.token = token
            if endpoint == "deviceregister":
                session.device_session = token
                session.state = "connected"
    if endpoint == "loginbyotp":
        session.phone = parameters.get("Username", session.phone)
        session.state = "authenticated" if parameters.get("OTPCode") else "otp_pending"
    elif endpoint == "loginbyusercredential":
        session.phone = parameters.get("Username", session.phone)
        session.state = "authenticated"
    session.save()


def live_call(session, action, parameters):
    parameters = normalize_inputs(action, parameters)
    validate_parameters(action, parameters)
    if action.get("requires_session", action.get("requires_auth", False)) and not session.token:
        raise PishkhanError("DEVICE_SESSION_REQUIRED", "ابتدا نشست پیشخوان را ایجاد یا وارد کنید.")
    try:
        result = trace_call(
            session, action, parameters, lambda: PishkhanClient().call(action, parameters, session.token)
        )
    except PishkhanError as exc:
        if exc.code == "AUTH_REQUIRED":
            session.state = "expired"
            session.token = ""
            session.device_session = ""
            session.save(update_fields=["state", "token", "device_session", "updated_at"])
        raise
    _update_account(session, action, parameters, result)
    return result


def create_session():
    session = AccountSession.objects.create(mode=settings.P24_MODE)
    result = session.public_dict()
    result["next_step"] = "p24_request_otp or p24_login_password"
    if session.mode == "demo":
        result["demo_otp"] = demo.DEMO_OTP
        result["notice"] = "نشست نمایشی است؛ هیچ پیامک یا درخواست واقعی ارسال نمی‌شود."
        session.token = "demo-device-session"
        session.save()
    else:
        try:
            action = find_action("DeviceRegister", "core")
            parameters = dict(registry().get("bootstrap_parameters", {}))
            parameters.update(
                {
                    "Application": settings.P24_APPLICATION,
                    "Origin": settings.P24_ORIGIN,
                    "Platform": settings.P24_PLATFORM,
                    "Version": settings.P24_VERSION,
                }
            )
            parameters.update(settings.P24_DEVICE_PARAMETERS)
            live_call(session, action, parameters)
            if not session.token:
                raise PishkhanError(
                    "BOOTSTRAP_SESSION_MISSING",
                    "پاسخ ثبت دستگاه، نشست معتبر برنگرداند.",
                    details={"outcome": "unknown"},
                )
            result.update(session.public_dict())
            result["bootstrap"] = "completed"
        except PishkhanError as exc:
            network_failure = exc.code in {"UPSTREAM_CONNECTION", "UPSTREAM_TIMEOUT", "UPSTREAM_HTTP"}
            result["bootstrap"] = "connection_failed" if network_failure else "requires_configuration"
            result["bootstrap_error"] = exc.as_dict()["error"]
            result["next_step"] = (
                "Check network/DNS and the configured P24_API_BASE_URL; no login or payment was attempted."
                if network_failure
                else "Inspect the upstream status and verified runtime settings; do not guess extra device fields."
            )
    return {"ok": True, **result}


def import_session(session_id, token):
    session = get_session(session_id)
    if session.mode != "live":
        raise PishkhanError("LIVE_MODE_REQUIRED", "ورود توکن واقعی فقط در حالت live مجاز است.")
    if not token.strip():
        raise PishkhanError("INVALID_TOKEN", "توکن خالی است.")
    session.token = token.strip()
    session.device_session = token.strip()
    session.state = "connected"
    session.save()
    return {
        "ok": True,
        **session.public_dict(),
        "validation": "Upstream validates this session on the next action.",
    }


def login(session_id, phone, *, otp=None, password=None, idempotency_key):
    session = get_session(session_id)
    phone = digits(phone)
    if password is not None:
        action_name = "LoginByUserCredential"
        parameters = {"Username": phone, "Password": password_digest(password)}
    else:
        action_name = "LoginByOTP"
        parameters = {"Username": phone, "OTPCode": digits(otp) if otp is not None else None}

    def perform():
        if session.mode == "demo":
            if otp is not None and digits(otp) != demo.DEMO_OTP:
                raise PishkhanError("INVALID_OTP", "کد نمایشی صحیح 123456 است.")
            session.phone = phone
            session.state = "authenticated" if otp is not None or password is not None else "otp_pending"
            session.save()
            return {
                "account": session.public_dict(),
                "demo": True,
                "message": "ورود نمایشی انجام شد."
                if session.state == "authenticated"
                else "کد نمایشی 123456؛ پیامکی ارسال نشده است.",
            }
        response = live_call(session, find_action(action_name, "core"), parameters)
        return {"account": session.public_dict(), "upstream": redact(response)}

    return execute_once(session, action_name, parameters, idempotency_key, perform)


def execute_action(session_id, action_id, parameters, idempotency_key):
    session = get_session(session_id)
    action = get_action(action_id)
    parameters = normalize_inputs(action, parameters)
    validate_parameters(action, parameters)
    if session.mode != "live":
        raise PishkhanError(
            "LIVE_ACTION_ONLY",
            "فراخوانی مستقیم قرارداد واقعی در حالت demo اجرا نمی‌شود؛ از ابزارهای نمایشی استفاده کنید.",
        )
    return execute_once(
        session,
        action_id,
        parameters,
        idempotency_key,
        lambda: live_call(session, action, parameters),
        service_id=resolve_service(action, parameters, current_request()),
    )


def _invoice(response):
    parameters = response.get("parameters", {})
    invoice = parameters.get("Invoice", {}) if isinstance(parameters, dict) else {}
    return invoice if isinstance(invoice, dict) else {}


def _present(value):
    return bool(value.strip()) if isinstance(value, str) else bool(value)


def _invoice_parameters(quote):
    data = quote.parameters.get("invoice", {})
    return data if isinstance(data, dict) else {}


def _prerequisite(data):
    prerequisite = data.get("Prerequisites")
    if not _present(prerequisite):
        return None
    if not isinstance(prerequisite, dict):
        return {"type": "unknown", "data": prerequisite}
    kind = str(prerequisite.get("Type", "unknown")).casefold()
    value = prerequisite.get("Value")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            pass
    return {"type": kind, "data": value}


def _set_stage(quote):
    """Follow the observed invoice branches without inventing a paid flag."""
    context = quote.parameters
    data = _invoice_parameters(quote)
    invoice = data.get("Invoice") or {}
    if not isinstance(invoice, dict):
        invoice = {}
    prerequisite = _prerequisite(data)
    message = (context.get("configuration") or {}).get("Message")
    if _present(message) and not context.get("configuration_acknowledged"):
        stage = "configuration_message"
    elif prerequisite:
        stage = "invoice_otp" if prerequisite["type"] == "otp" else "upstream_prerequisite"
    elif not context.get("purchase_key"):
        stage = "invoice_incomplete"
    elif (
        _present((invoice.get("Service") or {}).get("Summary")) or _present(data.get("TermsAndConditions"))
    ) and not context.get("preview_acknowledged"):
        stage = "invoice_preview"
    elif context.get("payment_completed"):
        stage = "ready"
    elif context.get("payment_started"):
        stage = "payment_pending"
    elif data.get("PaymentChannels"):
        stage = "payment_required"
    else:
        stage = "ready"
    context["stage"] = stage
    quote.parameters = context
    return stage


def _store_invoice(quote, response):
    data = response.get("parameters")
    if not isinstance(data, dict):
        raise PishkhanError(
            "INVOICE_FORMAT", "ساختار پاسخ صورتحساب قابل تفسیر نیست.", details={"outcome": "unknown"}
        )
    context = dict(quote.parameters)
    context["invoice"] = data
    invoice = data.get("Invoice") or {}
    if not isinstance(invoice, dict):
        raise PishkhanError(
            "INVOICE_FORMAT", "ساختار Invoice قابل تفسیر نیست.", details={"outcome": "unknown"}
        )
    key = invoice.get("PurchaseKey")
    if key:
        context["purchase_key"] = key
    raw_amount = invoice.get("Amount")
    quote.amount = (
        int(raw_amount) if isinstance(raw_amount, (int, str)) and str(raw_amount).isdigit() else None
    )
    quote.parameters = context
    _set_stage(quote)
    quote.save(update_fields=["parameters", "amount"])


def _register_invoice(session, quote, *, otp=None):
    inputs = dict(quote.parameters["input"])
    if otp is not None:
        action = get_action(quote.action_id)
        # Most public flows use OTPCode. Explicit action metadata can override
        # this only when an endpoint-specific spelling is source-confirmed.
        inputs[action.get("invoice_otp_field", "OTPCode")] = digits(otp)
    wire = {
        "Service": quote.parameters["service_name"],
        "Parameters": json.dumps(inputs, ensure_ascii=False, separators=(",", ":")),
    }
    response = live_call(session, find_action("InvoiceRegister", "services"), wire)
    _store_invoice(quote, response)
    return quote_dict(quote)


def quote_dict(quote):
    context = quote.parameters
    data = _invoice_parameters(quote)
    stage = context.get("stage", "ready" if quote.session.mode == "demo" else "invoice_incomplete")
    steps = {
        "configuration_message": "Read configuration_message, then p24_resume_inquiry with acknowledge_message=true.",
        "invoice_otp": "Provide the upstream service OTP to p24_resume_inquiry; this is separate from account login OTP.",
        "invoice_preview": "Read the returned summary/terms and amount, then p24_resume_inquiry with acknowledge_message=true.",
        "payment_required": "Select a Gateway from payment_channels, then p24_pay_quote.",
        "payment_pending": "Complete the returned gateway action, then p24_run_inquiry validates the purchased result upstream. Redirect alone is not payment proof.",
        "upstream_prerequisite": "Resolve the returned endpoint-specific prerequisite using its verified contract.",
        "result_prerequisite": "The result endpoint returned another prerequisite. Use the action-specific verified continuation fields; the inquiry is not complete.",
        "invoice_incomplete": "Inspect the upstream response; a usable purchase key or supported prerequisite was not returned.",
        "ready": "p24_run_inquiry",
        "completed": "p24_operation_status",
    }
    return {
        "ok": True,
        "quote_id": str(quote.pk),
        "request_id": str(quote.request_id) if quote.request_id else None,
        "mode": quote.session.mode,
        "service_id": quote.service_id,
        "action_id": quote.action_id,
        "amount": quote.amount,
        "payable": (data.get("Invoice") or {}).get("Payable")
        if isinstance(data.get("Invoice"), dict)
        else None,
        "currency": quote.currency,
        "expires_at": quote.expires_at.isoformat(),
        "stage": stage,
        "configuration_message": (context.get("configuration") or {}).get("Message"),
        "prerequisite": redact(_prerequisite(data)),
        "payment_channels": redact(data.get("PaymentChannels", [])),
        "invoice": redact(data),
        "next_step": steps.get(stage, "Inspect the upstream response."),
        "requires_user_action": stage not in {"ready", "completed"},
        "payment": redact(context.get("payment", {})),
        "demo": quote.session.mode == "demo",
    }


def prepare_inquiry(session_id, action_id, parameters, idempotency_key, service_name=None):
    session = get_session(session_id)
    action = get_action(action_id)
    if session.mode != "live":
        raise PishkhanError("LIVE_ACTION_ONLY", "برای نمونه از p24_quote_parcel_inquiry استفاده کنید.")
    if not isinstance(parameters, dict):
        raise PishkhanError("INVALID_PARAMETERS", "ورودی استعلام باید یک object باشد.")
    parameters = normalize_inputs(action, parameters)
    resolve_service(action, parameters, current_request())
    if action.get("invoice_input_schema"):
        validate_parameters({"parameters_schema": action["invoice_input_schema"]}, parameters)
    names = action.get("frontend_service_names", [])
    if isinstance(names, str):
        names = [names]
    if not names:
        raise PishkhanError(
            "WORKFLOW_CONTRACT_UNAVAILABLE",
            "نام خدمت برای جریان صورتحساب پیدا نشده است؛ قرارداد داخلی لازم است.",
        )
    if service_name is None and len(names) == 1:
        service_name = names[0]
    if service_name not in names:
        raise PishkhanError(
            "SERVICE_NAME_REQUIRED",
            "یکی از نام‌های مشاهده‌شدهٔ خدمت را انتخاب کنید.",
            details={"service_names": names},
        )
    wire = {
        "Service": service_name,
        "Parameters": json.dumps(parameters, ensure_ascii=False, separators=(",", ":")),
    }

    def perform():
        response = live_call(session, find_action("ConfigService", "core"), {"Service": service_name})
        configuration = response.get("parameters")
        if not isinstance(configuration, dict):
            raise PishkhanError("CONFIG_FORMAT", "ساختار تنظیمات خدمت قابل تفسیر نیست.")
        if configuration.get("Active") is False:
            raise PishkhanError("SERVICE_DISABLED", "ConfigService marks this service inactive.")
        quote = Quote.objects.create(
            request=current_request(),
            session=session,
            service_id=resolve_service(action, parameters, current_request()),
            action_id=action_id,
            parameters={
                "input": parameters,
                "service_name": service_name,
                "configuration": configuration,
                "stage": "registering_invoice",
            },
            amount=None,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        if _present(configuration.get("Message")):
            quote.parameters["stage"] = "configuration_message"
            quote.save(update_fields=["parameters"])
            return quote_dict(quote)
        return _register_invoice(session, quote)

    return execute_once(
        session,
        "prepare:" + action_id,
        wire,
        idempotency_key,
        perform,
        service_id=resolve_service(action, parameters, current_request()),
    )


def resume_inquiry(session_id, quote_id, idempotency_key, otp=None, acknowledge_message=False):
    session = get_session(session_id)
    quote = get_quote(session, quote_id)
    request = {"quote_id": str(quote.pk), "OTPCode": otp, "acknowledge_message": acknowledge_message}

    def perform():
        quote.refresh_from_db()
        if session.mode == "demo":
            return quote_dict(quote)
        stage = quote.parameters.get("stage")
        if stage == "configuration_message" and acknowledge_message:
            quote.parameters["configuration_acknowledged"] = True
            quote.save(update_fields=["parameters"])
            return _register_invoice(session, quote)
        if stage == "invoice_otp" and otp is not None:
            if not digits(otp):
                raise PishkhanError("OTP_REQUIRED", "کد دریافتی را وارد کنید.")
            return _register_invoice(session, quote, otp=otp)
        if stage == "invoice_preview" and acknowledge_message:
            quote.parameters["preview_acknowledged"] = True
            _set_stage(quote)
            quote.save(update_fields=["parameters"])
        return quote_dict(quote)

    return execute_once(
        session,
        "resume:" + quote.action_id,
        request,
        idempotency_key,
        perform,
        service_id=quote.service_id,
        request=quote.request,
    )


def quote_parcel(session_id, tracking_code, idempotency_key):
    session = get_session(session_id)
    tracking_code = digits(tracking_code)
    if session.mode == "live":
        action = find_action("PostPackagesStatus", "services")
        return prepare_inquiry(session_id, action["id"], {"TrackingCode": tracking_code}, idempotency_key)

    def perform():
        quote = Quote.objects.create(
            request=current_request(),
            session=session,
            service_id="posttracking",
            action_id="demo:posttracking",
            parameters={"input": {"tracking_code": tracking_code}},
            amount=50000,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        result = quote_dict(quote)
        result.update(
            {"next_step": "p24_run_parcel_inquiry", "notice": "هزینهٔ نمایشی؛ هیچ مبلغی برداشت نمی‌شود."}
        )
        return result

    return execute_once(
        session,
        "quote:posttracking",
        {"tracking_code": tracking_code},
        idempotency_key,
        perform,
        service_id="posttracking",
    )


def _retryable_inquiry_failure(operation):
    error = operation.result.get("error", {}) if isinstance(operation.result, dict) else {}
    return (
        operation.status == Operation.Status.FAILED
        and isinstance(error, dict)
        and error.get("code") in {"UPSTREAM_REJECTED", "AUTH_REQUIRED"}
    )


def _claim_inquiry_attempt(session, quote, parameters, idempotency_key, *, retry_failed):
    """Commit the latest-attempt pointer before contacting the purchased service.

    The quote lock serializes attempts using different retry keys. A second caller
    observes RUNNING and replays it. The old failed operation remains in history.
    """
    raw = json.dumps(
        {"action": quote.action_id, "parameters": parameters}, sort_keys=True, ensure_ascii=False
    )
    fingerprint = hashlib.sha256(raw.encode()).hexdigest()
    with transaction.atomic():
        current = Quote.objects.select_for_update().get(pk=quote.pk, session=session)
        latest = get_operation(session, current.operation_id) if current.operation_id else None
        if latest and (not retry_failed or not _retryable_inquiry_failure(latest)):
            return latest, False
        if retry_failed:
            if not latest or session.mode != "live" or not current.parameters.get("purchase_key"):
                raise PishkhanError(
                    "INQUIRY_NOT_RETRYABLE", "فقط دریافت نتیجهٔ خریداری‌شده با شکست قطعی قابل تکرار است."
                )
            if not idempotency_key or len(idempotency_key) > 128:
                raise PishkhanError(
                    "IDEMPOTENCY_KEY_REQUIRED", "یک idempotency_key ثابت برای تلاش مجدد لازم است."
                )
            digest = hashlib.sha256(idempotency_key.encode()).hexdigest()[:32]
            request_key = f"quote:{current.pk}:retry:{digest}"
        else:
            request_key = f"quote:{current.pk}"
        operation, created = Operation.objects.get_or_create(
            session=session,
            idempotency_key=request_key,
            defaults={
                "request": current.request,
                "action_id": quote.action_id,
                "service_id": quote.service_id,
                "request_hash": fingerprint,
                "request_data": redact(parameters),
            },
        )
        if operation.request_hash != fingerprint:
            raise PishkhanError(
                "IDEMPOTENCY_CONFLICT", "این کلید تلاش مجدد قبلاً برای ورودی متفاوت استفاده شده است."
            )
        if created:
            current.operation = operation
            current.save(update_fields=["operation"])
        return operation, created


def run_inquiry(session_id, quote_id, idempotency_key, *, retry_failed=False):
    session = get_session(session_id)
    # An already purchased result may be retrieved after the local quote timer.
    # The upstream purchase key remains authoritative for its own expiry.
    quote = get_quote(session, quote_id, allow_expired=True)
    if quote.operation_id:
        latest = get_operation(session, quote.operation_id)
        if not retry_failed or not _retryable_inquiry_failure(latest):
            return _operation_response(latest, replayed=True)
    elif retry_failed:
        raise PishkhanError(
            "INQUIRY_NOT_RETRYABLE", "ابتدا دریافت نتیجه را اجرا کنید؛ شکست قطعی قبلی وجود ندارد."
        )
    parameters = quote.parameters["input"]
    if session.mode == "demo":

        def executor():
            return {
                "demo": True,
                "data": demo.inquiry(quote.service_id, parameters),
                "charged_amount": 0,
                "simulated_amount": quote.amount,
                "currency": quote.currency,
            }
    else:
        stage = quote.parameters.get("stage")
        if stage not in {"ready", "payment_pending", "completed"}:
            return quote_dict(quote)
        if not quote.parameters.get("purchase_key"):
            return quote_dict(quote)
        action = get_action(quote.action_id)
        parameters = {**parameters, "PurchaseKey": quote.parameters["purchase_key"]}
        if retry_failed and action.get("requires_session", True) and not session.token:
            # Keep the original AUTH_REQUIRED attempt eligible while the user
            # reconnects; a missing local token must not consume a retry identity.
            raise PishkhanError(
                "DEVICE_SESSION_REQUIRED", "پیش از تکرار دریافت نتیجه، نشست پیشخوان را متصل کنید."
            )

        def executor():
            response = live_call(session, action, parameters)
            # Preserve changes made by invoice-status inspection while this
            # request was in flight, including the reserved operation pointer.
            quote.refresh_from_db()
            # A gateway redirect never reaches this branch by itself. Only the
            # authoritative service response can complete this result retrieval.
            data = response.get("parameters")
            if isinstance(data, dict) and _prerequisite(data):
                quote.parameters["stage"] = "result_prerequisite"
                quote.parameters["result_prerequisite"] = data["Prerequisites"]
                quote.save(update_fields=["parameters"])
                return {
                    **response,
                    "quote_id": str(quote.pk),
                    "stage": "result_prerequisite",
                    "requires_user_action": True,
                }
            quote.parameters["stage"] = "completed"
            quote.parameters["result_received"] = True
            quote.save(update_fields=["parameters"])
            return {**response, "quote_id": str(quote.pk), "stage": "completed"}

    operation, created = _claim_inquiry_attempt(
        session, quote, parameters, idempotency_key, retry_failed=retry_failed
    )
    if not created:
        return _operation_response(operation, replayed=True)
    return _complete_operation(operation, executor)


def simple_inquiry(session_id, service_id, parameters, idempotency_key):
    session = get_session(session_id)
    if session.mode == "demo":
        return execute_once(
            session,
            "demo:" + service_id,
            parameters,
            idempotency_key,
            lambda: {"demo": True, "data": demo.inquiry(service_id, parameters)},
            service_id=service_id,
        )
    if service_id == "freeway":
        endpoint, wire = "FreewayTollBills", {"PlateNumber": parameters["plate"], "OTPCode": None}
    elif service_id in {"electricity", "water"}:
        endpoint = "ElectricBills" if service_id == "electricity" else "WaterBills"
        wire = {"Identifier": parameters["bill_id"]}
    else:
        raise PishkhanError("WORKFLOW_CONTRACT_UNAVAILABLE", "جریان ساده برای این خدمت تعریف نشده است.")
    action = find_action(endpoint, "services")
    return prepare_inquiry(session_id, action["id"], wire, idempotency_key)


def pay_quote(session_id, quote_id, gateway, use_credit, idempotency_key):
    from apps.core.payments import pay_quote as pay

    return pay(session_id, quote_id, gateway, use_credit, idempotency_key)


def invoice_status(session_id, quote_id):
    session = get_session(session_id)
    quote = get_quote(session, quote_id, allow_expired=True)
    if session.mode == "demo":
        return {
            **quote_dict(quote),
            "operation": quote.operation.public_dict() if quote.operation_id else None,
        }
    if not quote.parameters.get("purchase_key"):
        return quote_dict(quote)
    result = live_call(
        session, find_action("InvoiceInfo", "core"), {"PurchaseKey": quote.parameters["purchase_key"]}
    )
    previous_stage = quote.parameters.get("stage")
    _store_invoice(quote, result)
    # InvoiceInfo's public contract does not establish a definitive paid flag.
    # Preserve gateway-pending/completed state; expose the upstream data as-is.
    if previous_stage in {"payment_pending", "completed"}:
        quote.parameters["stage"] = previous_stage
        quote.save(update_fields=["parameters"])
    return {**quote_dict(quote), "upstream": redact(result)}
