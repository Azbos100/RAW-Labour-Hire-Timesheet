"""
RAW Labour Hire - SMS Notification Service
Uses Cellcast (Australian SMS gateway, AUD-billed) for sending SMS messages.

SMS is the paid FALLBACK channel — notifications are sent as free in-app push first.
Public surface: send_sms / send_sms_sync / format_phone_number / brand_message /
get_sender + message templates.
"""

import os
from typing import Optional

import httpx

# Cellcast v3 REST API. Auth via APPKEY header. Docs: cellcast.com.au/api
CELLCAST_SEND_URL = "https://cellcast.com.au/api/v3/send-sms"
CELLCAST_API_KEY = os.getenv("CELLCAST_API_KEY")  # APPKEY from the Cellcast dashboard

# Optional custom Sender ID (e.g. "RAW Labour"). Max 11 chars (alpha) or 16 digits.
# IMPORTANT: a custom sender ID costs 1.3 credits/SMS on Cellcast vs 1 credit for the
# shared number, and is ONE-WAY (recipients can't reply). Leave blank to use the shared
# number (cheapest) — the company name is added to the body anyway (see brand_message).
CELLCAST_SENDER_ID = os.getenv("CELLCAST_SENDER_ID")

REQUEST_TIMEOUT = 20.0

# Default company name for messages
COMPANY_NAME = "RAW Labour Hire"

# Footer for automated, no-reply messages so recipients know how to reach us
# (shared numbers / alphanumeric sender IDs can't reliably receive replies).
CONTACT_FOOTER = "Reply not monitored - call or text Josh McPherson 0424 142 040"


def brand_message(message: str) -> str:
    """Make sure an outgoing SMS identifies RAW Labour Hire.

    When sending from the shared number (or an unfamiliar number) the recipient may
    just see an unknown sender, so adding the company name to the body guarantees they
    know who it's from. Skips adding it if the message already mentions the company.
    """
    msg = (message or "").strip()
    if "raw labour" not in msg.lower():
        msg = f"{msg}\n- {COMPANY_NAME}"
    return msg


def get_sender() -> Optional[str]:
    """The custom Sender ID for outbound SMS, or None to use Cellcast's shared number
    (cheapest). Returns None when no sender ID is configured."""
    s = (CELLCAST_SENDER_ID or "").strip()
    return s or None


def is_sms_configured() -> bool:
    """True when Cellcast credentials are present."""
    return bool(CELLCAST_API_KEY)


def format_phone_number(phone: str) -> str:
    """Format Australian phone number to E.164 format"""
    if not phone:
        return ""

    # Remove spaces, dashes, and brackets
    phone = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

    # Handle Australian numbers
    if phone.startswith("04"):
        # Convert 04xx to +614xx
        return "+61" + phone[1:]
    elif phone.startswith("+61"):
        return phone
    elif phone.startswith("61"):
        return "+" + phone
    elif phone.startswith("0"):
        return "+61" + phone[1:]

    # If already has + prefix, return as is
    if phone.startswith("+"):
        return phone

    # Default: assume Australian and add +61
    return "+61" + phone


def _headers() -> dict:
    return {
        "APPKEY": CELLCAST_API_KEY or "",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _build_payload(message: str, formatted_phone: str, message_type: str) -> dict:
    payload = {
        "sms_text": message,
        "numbers": [formatted_phone],
        "source": "RAW-Timesheet",
    }
    sender = get_sender()
    if sender:
        payload["from"] = sender
    # custom_string allows letters/numbers/dashes only — sanitise the message_type.
    tag = "".join(c if (c.isalnum() or c == "-") else "-" for c in (message_type or "custom"))
    if tag:
        payload["custom_string"] = tag[:50]
    return payload


def _parse_response(status_code: int, body: dict) -> dict:
    """Map a Cellcast response into our standard {success, message_sid|error} result."""
    meta = (body or {}).get("meta") or {}
    status = meta.get("status")

    if status_code == 200 and status == "SUCCESS":
        data = (body or {}).get("data") or {}
        messages = data.get("messages") if isinstance(data, dict) else None
        message_id = None
        if messages:
            message_id = (messages[0] or {}).get("message_id")
        low_alert = (body or {}).get("low_sms_alert")
        if low_alert:
            print(f"[SMS] Cellcast low-credit warning: {low_alert}")
        return {"success": True, "message_sid": message_id}

    # Error path (AUTH_FAILED / RECIPIENTS_ERROR / FIELD_INVALID / OVER_LIMIT / etc.)
    detail = (body or {}).get("msg") or status or f"HTTP {status_code}"
    error = f"{status}: {detail}" if status and status != detail else str(detail)
    return {"success": False, "error": error}


async def send_sms(
    to_phone: str,
    message: str,
    *,
    recipient_name: Optional[str] = None,
    worker_id: Optional[int] = None,
    message_type: str = "custom",
) -> dict:
    """
    Send an SMS message via Cellcast and record it in sms_logs for the admin audit trail.
    """
    from .sms_log import record_sms_log

    formatted_phone = format_phone_number(to_phone)

    if not is_sms_configured():
        result = {"success": False, "error": "SMS service not configured"}
        await record_sms_log(
            recipient_phone=formatted_phone or to_phone or "",
            recipient_name=recipient_name,
            worker_id=worker_id,
            message_type=message_type,
            message_preview=message,
            success=False,
            error=result["error"],
        )
        return result

    if not formatted_phone:
        result = {"success": False, "error": "Invalid phone number"}
        await record_sms_log(
            recipient_phone=to_phone or "",
            recipient_name=recipient_name,
            worker_id=worker_id,
            message_type=message_type,
            message_preview=message,
            success=False,
            error=result["error"],
        )
        return result

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(
                CELLCAST_SEND_URL,
                headers=_headers(),
                json=_build_payload(message, formatted_phone, message_type),
            )
        try:
            body = resp.json()
        except Exception:
            body = {}
        result = _parse_response(resp.status_code, body)
        result["to"] = formatted_phone
        if result.get("success"):
            print(f"[SMS] Sent to {formatted_phone}: {message[:50]}...")
        else:
            print(f"[SMS] Cellcast error to {formatted_phone}: {result.get('error')}")
    except Exception as e:
        print(f"[SMS] Error sending SMS: {e}")
        result = {"success": False, "error": str(e), "to": formatted_phone}

    await record_sms_log(
        recipient_phone=formatted_phone,
        recipient_name=recipient_name,
        worker_id=worker_id,
        message_type=message_type,
        message_preview=message,
        success=result.get("success", False),
        error=result.get("error"),
        provider_message_id=result.get("message_sid"),
    )
    return result


def send_sms_sync(
    to_phone: str,
    message: str,
    *,
    recipient_name: Optional[str] = None,
    worker_id: Optional[int] = None,
    message_type: str = "custom",
) -> dict:
    """Synchronous SMS send (for running many sends in a background thread)."""
    import asyncio
    from .sms_log import record_sms_log

    formatted_phone = format_phone_number(to_phone)

    def _log(result: dict) -> None:
        coro = record_sms_log(
            recipient_phone=formatted_phone or to_phone or "",
            recipient_name=recipient_name,
            worker_id=worker_id,
            message_type=message_type,
            message_preview=message,
            success=result.get("success", False),
            error=result.get("error"),
            provider_message_id=result.get("message_sid"),
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            asyncio.run(coro)

    if not is_sms_configured():
        result = {"success": False, "error": "SMS service not configured"}
        _log(result)
        return result
    if not formatted_phone:
        result = {"success": False, "error": "Invalid phone number"}
        _log(result)
        return result

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            resp = client.post(
                CELLCAST_SEND_URL,
                headers=_headers(),
                json=_build_payload(message, formatted_phone, message_type),
            )
        try:
            body = resp.json()
        except Exception:
            body = {}
        result = _parse_response(resp.status_code, body)
        result["to"] = formatted_phone
    except Exception as e:
        result = {"success": False, "error": str(e), "to": formatted_phone}

    _log(result)
    return result


# ==================== NOTIFICATION TEMPLATES ====================

def clock_in_reminder_message(worker_name: str) -> str:
    """Generate clock-in reminder message"""
    return f"Hi {worker_name}, this is a reminder from {COMPANY_NAME} to clock in for your shift. Please open the RAW Timesheet app to clock in.\n{CONTACT_FOOTER}"


def clock_out_reminder_message(worker_name: str) -> str:
    """Generate clock-out reminder message"""
    return f"Hi {worker_name}, this is a reminder from {COMPANY_NAME} to clock out. Please open the RAW Timesheet app to clock out before leaving site.\n{CONTACT_FOOTER}"


def timesheet_approved_message(worker_name: str, docket_number: str) -> str:
    """Generate timesheet approval notification"""
    return f"Hi {worker_name}, your timesheet #{docket_number} has been approved by {COMPANY_NAME}.\n{CONTACT_FOOTER}"


def timesheet_rejected_message(worker_name: str, docket_number: str) -> str:
    """Generate timesheet rejection notification"""
    return f"Hi {worker_name}, your timesheet #{docket_number} needs attention. Please check the RAW Timesheet app for details.\n{CONTACT_FOOTER}"
