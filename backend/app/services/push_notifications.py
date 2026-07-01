"""
Expo Push Notification Service
Send push notifications via Expo's push notification service
"""

import httpx
from typing import List, Optional

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_RECEIPT_URL = "https://exp.host/--/api/v2/push/getReceipts"

# Expo error codes that mean the token is permanently invalid (app uninstalled /
# reinstalled / token expired). When we see one, clear the stored token so future
# notifications go straight to SMS and the app re-registers a fresh token on launch.
DEAD_TOKEN_ERRORS = {"DeviceNotRegistered"}


def _ticket(result) -> Optional[dict]:
    """Pull the single push ticket dict out of an Expo /send response."""
    data = (result or {}).get("data")
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def ticket_status(result) -> Optional[str]:
    """'ok' or 'error' for a /send response, or None if unknown."""
    t = _ticket(result)
    return t.get("status") if isinstance(t, dict) else None


def ticket_error_code(result) -> Optional[str]:
    """Expo error tickets: {"status":"error","details":{"error":"DeviceNotRegistered"}}."""
    t = _ticket(result)
    if isinstance(t, dict) and t.get("status") == "error":
        return (t.get("details") or {}).get("error") or "error"
    return None


def ticket_id(result) -> Optional[str]:
    """The receipt id for a successfully-accepted ('ok') push, else None."""
    t = _ticket(result)
    if isinstance(t, dict) and t.get("status") == "ok":
        return t.get("id")
    return None


def is_dead_token_result(push_result) -> bool:
    """True when the send result shows a permanently-invalid token."""
    return ticket_error_code((push_result or {}).get("result")) in DEAD_TOKEN_ERRORS


async def get_push_receipts(receipt_ids: List[str]) -> dict:
    """Fetch delivery receipts for the given ticket ids. Returns a dict keyed by
    ticket id (only ids whose receipt is ready are present)."""
    if not receipt_ids:
        return {}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                EXPO_RECEIPT_URL,
                json={"ids": receipt_ids},
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
        body = resp.json()
        return (body or {}).get("data") or {}
    except Exception as e:
        print(f"Push receipt fetch error: {e}")
        return {}


async def send_push_notification(
    push_token: str,
    title: str,
    body: str,
    data: Optional[dict] = None
) -> dict:
    """
    Send a push notification via Expo Push Service
    
    Args:
        push_token: Expo push token (starts with ExponentPushToken[...])
        title: Notification title
        body: Notification body text
        data: Optional additional data to include
    
    Returns:
        Response from Expo push service
    """
    if not push_token or not push_token.startswith("ExponentPushToken"):
        return {"success": False, "error": "Invalid push token"}
    
    message = {
        "to": push_token,
        "sound": "default",
        "title": title,
        "body": body,
        "priority": "high",
    }
    
    if data:
        message["data"] = data
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                EXPO_PUSH_URL,
                json=message,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                }
            )
            result = response.json()
            print(f"Push notification sent: {result}")
            return {"success": True, "result": result}
    except Exception as e:
        print(f"Push notification error: {e}")
        return {"success": False, "error": str(e)}


async def send_push_notifications_batch(
    messages: List[dict]
) -> dict:
    """
    Send multiple push notifications in a batch
    
    Args:
        messages: List of message dicts with keys: push_token, title, body, data (optional)
    
    Returns:
        Response from Expo push service
    """
    formatted_messages = []
    for msg in messages:
        if not msg.get("push_token", "").startswith("ExponentPushToken"):
            continue
        formatted = {
            "to": msg["push_token"],
            "sound": "default",
            "title": msg["title"],
            "body": msg["body"],
            "priority": "high",
        }
        if msg.get("data"):
            formatted["data"] = msg["data"]
        formatted_messages.append(formatted)
    
    if not formatted_messages:
        return {"success": False, "error": "No valid push tokens"}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                EXPO_PUSH_URL,
                json=formatted_messages,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                }
            )
            result = response.json()
            print(f"Batch push notifications sent: {result}")
            return {"success": True, "result": result}
    except Exception as e:
        print(f"Batch push notification error: {e}")
        return {"success": False, "error": str(e)}
