"""
Expo Push Notification Service
Send push notifications via Expo's push notification service
"""

import httpx
from typing import List, Optional

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


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
