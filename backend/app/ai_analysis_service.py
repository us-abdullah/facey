"""
AI Analysis Service:
  1. NVIDIA Nemotron Nano 12B VL v2  – visual analysis of the incident frame
  2. Anthropic Claude                – formal written security incident report

Env vars:
  NVIDIA_API_KEY     – NVIDIA NIM API key (https://build.nvidia.com)
  ANTHROPIC_API_KEY  – Anthropic Claude API key
"""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

NEMOTRON_MODEL = "nvidia/nemotron-nano-12b-v2-vl"
NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
CLAUDE_MODEL = "claude-opus-4-5"

LOCATION = "1/2 Bond Street, HOF Capital Building, 2nd Floor"


# ---------------------------------------------------------------------------
# Nemotron VLM – analyze the incident frame
# ---------------------------------------------------------------------------

def _encode_image(image_bytes: bytes, max_width: int = 640) -> Optional[str]:
    """Decode, resize, and base64-encode image for the API."""
    try:
        import cv2
        import numpy as np
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        h, w = img.shape[:2]
        if w > max_width:
            scale = max_width / w
            img = cv2.resize(img, (max_width, int(h * scale)), interpolation=cv2.INTER_AREA)
        _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.b64encode(buf.tobytes()).decode("utf-8")
    except Exception as e:
        logger.warning("Image encode failed: %s", e)
        return None


def analyze_frame_with_nemotron(
    image_bytes: bytes,
    zone_name: str,
    person_name: str,
) -> dict:
    """
    Send the incident frame to NVIDIA Nemotron Nano 12B VL v2.
    Returns a dict with keys: available, human_confirmed, physical_description,
    behavior, threat_level, observations, confidence.
    """
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        return {
            "available": False,
            "human_confirmed": True,
            "physical_description": "Visual analysis unavailable – NVIDIA_API_KEY not configured.",
            "behavior": "Unauthorized presence in restricted zone.",
            "threat_level": "HIGH",
            "observations": "Automated zone detection triggered. Manual review required.",
            "confidence": "n/a",
        }

    img_b64 = _encode_image(image_bytes)
    if not img_b64:
        return {
            "available": False,
            "human_confirmed": True,
            "physical_description": "Could not decode incident frame for VLM analysis.",
            "behavior": "Unknown.",
            "threat_level": "HIGH",
            "observations": "Frame decoding failed.",
            "confidence": "n/a",
        }

    prompt = (
        f'You are a security AI system analyzing a CCTV camera frame.\n\n'
        f'Context: An automated sensor detected an unauthorized individual in the "{zone_name}" restricted zone '
        f'at {LOCATION}. The subject was identified as "{person_name}" '
        f'({"registered in the system" if person_name.lower() != "unknown" else "not found in the face database"}).\n\n'
        f'Analyze the image and return ONLY a JSON object with these keys:\n'
        f'{{\n'
        f'  "human_confirmed": <true|false>,\n'
        f'  "physical_description": "<clothing, build, approximate age, distinguishing features>",\n'
        f'  "behavior": "<what the person is doing, posture, movement direction>",\n'
        f'  "threat_level": "<LOW|MEDIUM|HIGH>",\n'
        f'  "observations": "<any security-relevant observations: items carried, access methods, demeanor>",\n'
        f'  "confidence": "<high|medium|low>"\n'
        f'}}\n\n'
        f'Return only valid JSON, no prose.'
    )

    try:
        import requests
        r = requests.post(
            NVIDIA_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": NEMOTRON_MODEL,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/jpeg;base64,{img_b64}"
                        }},
                    ],
                }],
                "max_tokens": 512,
                "temperature": 0.05,
            },
            timeout=45,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        # Extract JSON from the response
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(content[start:end])
            return {"available": True, **data}
        # Fallback: return raw content as observation
        return {
            "available": True,
            "human_confirmed": True,
            "physical_description": "See observations.",
            "behavior": "See observations.",
            "threat_level": "HIGH",
            "observations": content,
            "confidence": "low",
        }
    except Exception as e:
        logger.exception("Nemotron analysis failed: %s", e)
        return {
            "available": False,
            "human_confirmed": True,
            "physical_description": f"VLM analysis failed: {e}",
            "behavior": "Unknown.",
            "threat_level": "HIGH",
            "observations": "Analysis error – manual review required.",
            "confidence": "n/a",
        }


# ---------------------------------------------------------------------------
# Claude – formal written incident report
# ---------------------------------------------------------------------------

def write_report_with_claude(alert: dict, nemotron: dict) -> str:
    """
    Use Claude to write a formal, professional security incident report.
    Falls back to a well-structured template if ANTHROPIC_API_KEY is not set.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _fallback_report(alert, nemotron)

    person_name = alert.get("person_name", "Unknown")
    zone_name = alert.get("zone_name", "Analyst Zone")
    ts = alert.get("timestamp", "N/A")
    feed_id = alert.get("feed_id", 0)
    alert_type = alert.get("alert_type", "zone_presence").replace("_", " ").title()

    subject_status = (
        f'Registered person named "{person_name}"'
        if person_name.lower() != "unknown"
        else "Unregistered individual — no match found in the HOF Capital face database"
    )

    vlm_section = ""
    if nemotron.get("available"):
        vlm_section = (
            f"Physical Description: {nemotron.get('physical_description', 'N/A')}\n"
            f"Observed Behavior: {nemotron.get('behavior', 'N/A')}\n"
            f"Threat Level (VLM): {nemotron.get('threat_level', 'HIGH')}\n"
            f"Security Observations: {nemotron.get('observations', 'N/A')}\n"
            f"Analysis Confidence: {nemotron.get('confidence', 'N/A')}\n"
            f"Human Presence Confirmed: {nemotron.get('human_confirmed', True)}"
        )
    else:
        vlm_section = (
            "VLM visual analysis was unavailable for this incident. "
            "Manual review of the attached CCTV footage is required."
        )

    prompt = (
        f"You are a senior security operations officer at HOF Capital Management, "
        f"a hedge fund located at {LOCATION}, Analyst Zone. "
        f"Write a formal, professional security incident report based strictly on the data below.\n\n"
        f"INCIDENT DATA\n"
        f"Incident ID:   {alert.get('alert_id', 'N/A')}\n"
        f"Date/Time:     {ts}\n"
        f"Location:      {LOCATION}, {zone_name}\n"
        f"Camera Feed:   Camera Feed {feed_id + 1}\n"
        f"Alert Type:    {alert_type}\n"
        f"Subject:       {subject_status}\n"
        f"Initial Log:   {alert.get('details', 'Unauthorized presence detected in restricted zone.')}\n\n"
        f"VLM ANALYSIS (NVIDIA Nemotron Nano 12B VL v2)\n{vlm_section}\n\n"
        f"Write the report with these exact section headings (plain text, no markdown):\n"
        f"EXECUTIVE SUMMARY\n"
        f"INCIDENT DETAILS\n"
        f"SUBJECT PROFILE\n"
        f"VLM ANALYSIS SUMMARY\n"
        f"RISK ASSESSMENT\n"
        f"RECOMMENDED IMMEDIATE ACTIONS\n"
        f"COMPLIANCE NOTES\n\n"
        f"Requirements: formal security operations English, factual and concise, "
        f"no markdown symbols, no bullet dashes (use numbered lists), reference HOF Capital and the location. "
        f"Total length: approximately 350-450 words."
    )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1400,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception as e:
        logger.exception("Claude report writing failed: %s", e)
        return _fallback_report(alert, nemotron)


def _fallback_report(alert: dict, nemotron: dict) -> str:
    name = alert.get("person_name", "Unknown")
    zone = alert.get("zone_name", "Analyst Zone")
    ts = alert.get("timestamp", "N/A")
    feed = alert.get("feed_id", 0) + 1
    tl = nemotron.get("threat_level", "HIGH")
    phys = nemotron.get("physical_description", "Not available.")
    behavior = nemotron.get("behavior", "Not available.")
    obs = nemotron.get("observations", "Not available.")

    subject_line = (
        f"{name}" if name.lower() != "unknown"
        else "Unknown — No match in HOF Capital face database"
    )

    return (
        f"EXECUTIVE SUMMARY\n"
        f"An unauthorized individual was detected in the {zone} at {LOCATION} on {ts}. "
        f"The individual did not match any registered profile in the HOF Capital security database. "
        f"Immediate investigation and review of security footage is recommended.\n\n"
        f"INCIDENT DETAILS\n"
        f"Date and Time: {ts}\n"
        f"Location: {LOCATION}, {zone}\n"
        f"Camera Feed: Camera Feed {feed}\n"
        f"Detection Method: Automated restricted zone presence detection\n"
        f"Alert Classification: Unauthorized Zone Access\n\n"
        f"SUBJECT PROFILE\n"
        f"Identified Name: {subject_line}\n"
        f"Access Status: Unauthorized\n"
        f"Registration Status: Not registered in the face recognition system\n\n"
        f"VLM ANALYSIS SUMMARY\n"
        f"Analysis System: NVIDIA Nemotron Nano 12B VL v2\n"
        f"Physical Description: {phys}\n"
        f"Observed Behavior: {behavior}\n"
        f"Security Observations: {obs}\n"
        f"Threat Level: {tl}\n\n"
        f"RISK ASSESSMENT\n"
        f"This incident is classified as {tl} priority. The Analyst Zone contains sensitive financial workstations, "
        f"proprietary trading data, and confidential HOF Capital research materials. Unauthorized access to this "
        f"area represents a significant security and compliance risk.\n\n"
        f"RECOMMENDED IMMEDIATE ACTIONS\n"
        f"1. Review all CCTV footage from the time window indicated.\n"
        f"2. Notify the floor manager and head of security immediately.\n"
        f"3. Determine whether the individual was escorted or accessed the zone independently.\n"
        f"4. Check building access logs (badge swipes, elevator records) for the same time period.\n"
        f"5. Consider temporary restricted access to the Analyst Zone pending investigation.\n"
        f"6. File a formal incident report with the compliance team.\n\n"
        f"COMPLIANCE NOTES\n"
        f"This incident must be documented and retained per HOF Capital's security incident response policy. "
        f"If sensitive data may have been compromised, escalate to the Chief Compliance Officer within 24 hours."
    )
