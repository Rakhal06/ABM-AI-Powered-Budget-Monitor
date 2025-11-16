# utils/notify.py
import os
import logging
from typing import Tuple, Optional

try:
    from twilio.rest import Client
except Exception:
    Client = None

logger = logging.getLogger(__name__)

def _get_twilio_credentials():
    """
    Return (account_sid, auth_token, from_number, to_number) from environment or Streamlit secrets.
    - Streamlit secrets keys (preferred): TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM, TWILIO_TO
    - Environment variables fallback: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM, TWILIO_TO
    """
    # prefer environment since this file may be used outside streamlit; streamlit secrets will also be in os.environ when run via streamlit
    sid = os.environ.get("TWILIO_ACCOUNT_SID") or os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN") or os.environ.get("TWILIO_AUTH_TOKEN")
    from_num = os.environ.get("TWILIO_FROM") or os.environ.get("TWILIO_FROM")
    to_num = os.environ.get("TWILIO_TO") or os.environ.get("TWILIO_TO")
    return sid, token, from_num, to_num


def send_sms_via_twilio(body: str, to: Optional[str] = None) -> Tuple[bool, str]:
    """
    Send an SMS using Twilio.
    - body: message body
    - to: optional override for destination phone number (E.164 format, e.g. +9199...)
    Returns (success, message_or_error)
    """
    if Client is None:
        return False, "twilio library not installed (pip install twilio)."

    sid, token, from_num, default_to = _get_twilio_credentials()
    if not sid or not token or not from_num:
        return False, "Missing Twilio credentials. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM (and TWILIO_TO)."

    dest = to if to else default_to
    if not dest:
        return False, "No destination phone number provided (TWILIO_TO)."

    try:
        client = Client(sid, token)
        msg = client.messages.create(
            body=body,
            from_=from_num,
            to=dest
        )
        return True, f"Sent message, SID={msg.sid}"
    except Exception as e:
        logger.exception("Failed to send SMS")
        return False, str(e)
