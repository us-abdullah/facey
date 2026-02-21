"""Twilio SMS alerting for restricted-zone violations."""

import logging
import os

logger = logging.getLogger(__name__)

# ── Defaults ──────────────────────────────────────────────────────────────
DEFAULT_ALERT_TO = "+18777804236"
DEFAULT_MESSAGING_SERVICE_SID = "MGbeabe48cb26d252c506513ebe01f22b9"
ZONE_ALERT_BODY = "Intruder detected! check dashboard in analyst area"


def send_zone_alert_sms(
    zone_name: str,
    alert_type: str,
    person_name: str,
    details: str,
) -> bool:
    """Send an SMS via Twilio when an unauthorized person is in a restricted zone.

    Reads TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN from env.  Optionally reads
    TWILIO_ALERT_TO and TWILIO_MESSAGING_SERVICE_SID to override the defaults.

    Returns True on success, False otherwise.
    """
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")

    if not account_sid or not auth_token:
        logger.warning("TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN not set – skipping SMS")
        return False

    to_number = os.environ.get("TWILIO_ALERT_TO", DEFAULT_ALERT_TO)
    messaging_service_sid = os.environ.get(
        "TWILIO_MESSAGING_SERVICE_SID", DEFAULT_MESSAGING_SERVICE_SID
    )

    try:
        from twilio.rest import Client

        client = Client(account_sid, auth_token)
        message = client.messages.create(
            body=ZONE_ALERT_BODY,
            to=to_number,
            messaging_service_sid=messaging_service_sid,
        )
        logger.info(
            "Twilio SMS sent (sid=%s) for zone=%s person=%s",
            message.sid,
            zone_name,
            person_name,
        )
        return True
    except Exception:
        logger.exception(
            "Failed to send Twilio SMS for zone=%s person=%s",
            zone_name,
            person_name,
        )
        return False
