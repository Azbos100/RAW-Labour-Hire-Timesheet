"""
RAW Labour Hire - SMS Notification Service
Uses Twilio for sending SMS messages
"""

import os
from typing import Optional
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

# Twilio configuration from environment variables
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")  # Your Twilio phone number

# Default company name for messages
COMPANY_NAME = "RAW Labour Hire"


def get_twilio_client() -> Optional[Client]:
    """Get Twilio client if credentials are configured"""
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
        print("[SMS] Twilio not configured - missing credentials")
        return None
    
    try:
        return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    except Exception as e:
        print(f"[SMS] Error creating Twilio client: {e}")
        return None


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


async def send_sms(to_phone: str, message: str) -> dict:
    """
    Send an SMS message
    
    Args:
        to_phone: Recipient phone number
        message: Message text (max 160 chars for single SMS)
    
    Returns:
        dict with success status and message SID or error
    """
    client = get_twilio_client()
    
    if not client:
        return {
            "success": False,
            "error": "SMS service not configured"
        }
    
    formatted_phone = format_phone_number(to_phone)
    
    if not formatted_phone:
        return {
            "success": False,
            "error": "Invalid phone number"
        }
    
    try:
        message_obj = client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=formatted_phone
        )
        
        print(f"[SMS] Sent to {formatted_phone}: {message[:50]}...")
        
        return {
            "success": True,
            "message_sid": message_obj.sid,
            "to": formatted_phone
        }
    
    except TwilioRestException as e:
        print(f"[SMS] Twilio error: {e}")
        return {
            "success": False,
            "error": str(e)
        }
    except Exception as e:
        print(f"[SMS] Error sending SMS: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# ==================== NOTIFICATION TEMPLATES ====================

def clock_in_reminder_message(worker_name: str) -> str:
    """Generate clock-in reminder message"""
    return f"Hi {worker_name}, this is a reminder from {COMPANY_NAME} to clock in for your shift. Please open the RAW Timesheet app to clock in."


def clock_out_reminder_message(worker_name: str) -> str:
    """Generate clock-out reminder message"""
    return f"Hi {worker_name}, this is a reminder from {COMPANY_NAME} to clock out. Please open the RAW Timesheet app to clock out before leaving site."


def timesheet_approved_message(worker_name: str, docket_number: str) -> str:
    """Generate timesheet approval notification"""
    return f"Hi {worker_name}, your timesheet #{docket_number} has been approved by {COMPANY_NAME}."


def timesheet_rejected_message(worker_name: str, docket_number: str) -> str:
    """Generate timesheet rejection notification"""
    return f"Hi {worker_name}, your timesheet #{docket_number} needs attention. Please check the RAW Timesheet app for details."
