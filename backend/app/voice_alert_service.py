"""
Voice alert service: ElevenLabs TTS + Twilio outbound call.

When an unknown person is detected in the Analyst Zone, we:
1. Generate TTS with ElevenLabs: "Security violation detected in Analyst Zone, please check the dashboard for the security footage"
2. Save MP3 to recordings/{alert_id}_announcement.mp3
3. Place outbound call(s) to C-level phone numbers via Twilio; when answered, Twilio fetches our TwiML URL and plays the MP3.

Requires:
- ELEVENLABS_API_KEY (or XI_API_KEY)
- TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER (from number)
- C_LEVEL_PHONE_NUMBERS (comma-separated, e.g. +15551234567,+15559876543)
- PUBLIC_BASE_URL (public URL of this backend so Twilio can fetch TwiML and MP3, e.g. https://xxx.ngrok.io)

If any are missing, voice alerts are skipped (no exception).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

# Exact message for unknown person in Analyst Zone (TTS + notifications)
VIOLATION_MESSAGE = (
    "Unknown intruder detected in the Analyst Zone, "
    "please visit the dashboard to acknowledge or resolve the security issue!"
)


def _get_elevenlabs_key() -> str | None:
    return os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("XI_API_KEY")


def _get_twilio_config() -> tuple[str, str, str] | None:
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_num = os.environ.get("TWILIO_PHONE_NUMBER")
    if sid and token and from_num:
        return (sid, token, from_num)
    return None


def _get_c_level_phones() -> List[str]:
    raw = os.environ.get("C_LEVEL_PHONE_NUMBERS", "")
    return [p.strip() for p in raw.split(",") if p.strip()]


def _get_public_base_url() -> str | None:
    return os.environ.get("PUBLIC_BASE_URL") or os.environ.get("BASE_URL")


def generate_announcement_mp3(
    alert_id: str,
    message: str,
    data_dir: Path,
    voice_id: str = "21m00Tcm4TlvDq8ikWAM",  # Rachel – default ElevenLabs voice
) -> Path | None:
    """
    Generate TTS with ElevenLabs and save to recordings/{alert_id}_announcement.mp3.
    Returns path to the file, or None if ElevenLabs is not configured or fails.
    """
    api_key = _get_elevenlabs_key()
    if not api_key:
        logger.debug("ElevenLabs API key not set; skipping TTS")
        return None

    try:
        import requests
    except ImportError:
        logger.warning("requests not installed; cannot call ElevenLabs")
        return None

    rec_dir = data_dir / "recordings"
    rec_dir.mkdir(parents=True, exist_ok=True)
    out_path = rec_dir / f"{alert_id}_announcement.mp3"

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    params = {"output_format": "mp3_44100_128"}
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key,
    }
    payload = {
        "text": message,
        "model_id": "eleven_multilingual_v2",
    }

    try:
        r = requests.post(url, params=params, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        out_path.write_bytes(r.content)
        logger.info("ElevenLabs TTS saved to %s", out_path)
        return out_path
    except Exception as e:
        logger.exception("ElevenLabs TTS failed: %s", e)
        return None


def trigger_violation_calls(
    alert_id: str,
    public_base_url: str,
    phone_numbers: List[str],
) -> None:
    """
    Place outbound Twilio call to each number. When the call is answered, Twilio
    requests public_base_url/api/security/voice/twiml/{alert_id} and plays the
    returned TwiML (which contains <Play> to our MP3 URL).
    """
    twilio = _get_twilio_config()
    if not twilio:
        logger.debug("Twilio not configured; skipping outbound call")
        return
    if not phone_numbers:
        logger.debug("No C-level phone numbers configured")
        return

    sid, token, from_num = twilio
    base = public_base_url.rstrip("/")
    twiml_url = f"{base}/api/security/voice/twiml/{alert_id}"

    try:
        from twilio.rest import Client
    except ImportError:
        logger.warning("twilio not installed; cannot place call")
        return

    client = Client(sid, token)
    for to_num in phone_numbers:
        try:
            client.calls.create(
                to=to_num,
                from_=from_num,
                url=twiml_url,
                method="GET",
                timeout=15,
            )
            logger.info("Twilio call initiated to %s for alert %s", to_num, alert_id)
        except Exception as e:
            logger.exception("Twilio call to %s failed: %s", to_num, e)


def trigger_analyst_zone_voice_alert(alert_id: str, data_dir: Path) -> None:
    """
    Full flow for "Unknown person in Analyst Zone":
    1. Generate MP3 with ElevenLabs (exact violation message).
    2. If PUBLIC_BASE_URL and Twilio + phones are set, place call(s).

    Safe to call from sync code; runs in same process (TTS is fast; Twilio
    create is a quick HTTP call – the actual ringing is asynchronous).
    """
    path = generate_announcement_mp3(alert_id, VIOLATION_MESSAGE, data_dir)
    if not path:
        return

    base_url = _get_public_base_url()
    phones = _get_c_level_phones()
    if base_url and phones:
        trigger_violation_calls(alert_id, base_url, phones)
    else:
        if not base_url:
            logger.debug("PUBLIC_BASE_URL not set; Twilio cannot fetch TwiML/MP3")
        if not phones:
            logger.debug("C_LEVEL_PHONE_NUMBERS not set")
