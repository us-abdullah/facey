"""ElevenLabs TTS for security alert audio announcements.

Generates spoken alerts that auto-play on the dashboard when
URGENT or CRITICAL escalations are detected.

Env vars:
  ELEVENLABS_API_KEY  – ElevenLabs API key (sk_...)
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech"

# Rachel – clear, professional female voice (built-in, no cloning needed)
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"

# Model: eleven_turbo_v2_5 is fast + high quality
DEFAULT_MODEL_ID = "eleven_turbo_v2_5"


def generate_alert_audio(
    text: str,
    voice_id: str = DEFAULT_VOICE_ID,
    model_id: str = DEFAULT_MODEL_ID,
) -> Optional[bytes]:
    """Convert text to speech via ElevenLabs. Returns MP3 bytes or None."""
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        logger.warning("ELEVENLABS_API_KEY not set – skipping TTS")
        return None

    try:
        r = requests.post(
            f"{ELEVENLABS_TTS_URL}/{voice_id}",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": model_id,
                "voice_settings": {
                    "stability": 0.75,
                    "similarity_boost": 0.85,
                    "style": 0.15,
                    "use_speaker_boost": True,
                },
            },
            timeout=30,
        )
        r.raise_for_status()
        logger.info("ElevenLabs TTS generated %d bytes", len(r.content))
        return r.content
    except Exception:
        logger.exception("ElevenLabs TTS failed")
        return None


def build_alert_announcement(
    alert: dict,
    escalation: Optional[dict] = None,
    nemotron: Optional[dict] = None,
) -> str:
    """Build a concise spoken announcement for a security alert."""
    level = "Critical" if not escalation else escalation.get("escalation_level", "Critical").capitalize()
    zone = alert.get("zone_name", "restricted zone")
    person = alert.get("person_name", "Unknown individual")

    if person.lower() == "unknown":
        person_desc = "An unregistered individual"
    else:
        person_desc = person

    behavior = ""
    if nemotron and nemotron.get("available"):
        behavior = f" {nemotron.get('behavior', '')}"

    response = ""
    if escalation and escalation.get("recommended_response"):
        response = f" {escalation['recommended_response']}"

    text = (
        f"Security alert. {level} level. "
        f"{person_desc} detected in {zone}.{behavior}"
        f"{response} "
        f"Check dashboard for details."
    )
    return text
