"""Supabase integration for HOF Capital Security System.

Persists security incidents, registered persons, and visitor logs to Supabase.
Uploads GIF recordings, PDF reports, and threat images to Supabase Storage.

Falls back gracefully when Supabase is unavailable (local JSON still works).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    """Lazy-init the Supabase client. Returns None if creds are missing."""
    global _client
    if _client is not None:
        return _client

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        logger.warning("SUPABASE_URL / SUPABASE_ANON_KEY not set – Supabase disabled")
        return None

    try:
        from supabase import create_client
        _client = create_client(url, key)
        logger.info("Supabase client initialized: %s", url)
        return _client
    except Exception:
        logger.exception("Failed to create Supabase client")
        return None


# ── Security Incidents ─────────────────────────────────────────────────────

def upsert_incident(alert: dict) -> bool:
    """Insert or update a security incident row. Returns True on success."""
    client = _get_client()
    if not client:
        return False

    row = {
        "alert_id": alert["alert_id"],
        "timestamp": alert.get("timestamp"),
        "alert_type": alert.get("alert_type"),
        "feed_id": alert.get("feed_id", 0),
        "person_name": alert.get("person_name", "Unknown"),
        "person_role": alert.get("person_role"),
        "authorized": alert.get("authorized", False),
        "zone_name": alert.get("zone_name"),
        "details": alert.get("details"),
        "acknowledged": alert.get("acknowledged", False),
        "resolution": alert.get("resolution"),
        "recording_url": alert.get("recording_url"),
        "report_url": alert.get("report_url"),
        "threat_image_url": alert.get("threat_image_url"),
        "escalation_level": alert.get("escalation_level"),
        "escalation_reasoning": alert.get("escalation_reasoning"),
    }
    try:
        client.table("security_incidents").upsert(row, on_conflict="alert_id").execute()
        return True
    except Exception:
        logger.exception("Failed to upsert incident %s", alert.get("alert_id"))
        return False


def update_incident_field(alert_id: str, **fields) -> bool:
    """Update specific fields on an existing incident."""
    client = _get_client()
    if not client:
        return False
    try:
        client.table("security_incidents").update(fields).eq("alert_id", alert_id).execute()
        return True
    except Exception:
        logger.exception("Failed to update incident %s", alert_id)
        return False


def resolve_incident(alert_id: str, resolution: str) -> bool:
    """Mark an incident as acknowledged or problem_fixed."""
    return update_incident_field(
        alert_id,
        acknowledged=True,
        resolution=resolution,
    )


def get_incidents(limit: int = 200) -> list[dict]:
    """Fetch recent incidents from Supabase, newest first."""
    client = _get_client()
    if not client:
        return []
    try:
        resp = (
            client.table("security_incidents")
            .select("*")
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )
        return resp.data or []
    except Exception:
        logger.exception("Failed to fetch incidents")
        return []


def clear_incidents() -> bool:
    """Delete all incidents from Supabase."""
    client = _get_client()
    if not client:
        return False
    try:
        client.table("security_incidents").delete().neq("alert_id", "").execute()
        return True
    except Exception:
        logger.exception("Failed to clear incidents")
        return False


# ── Registered Persons ─────────────────────────────────────────────────────

def upsert_person(identity_id: str, name: str, role: str, authorized: bool = True) -> bool:
    """Insert or update a registered person."""
    client = _get_client()
    if not client:
        return False

    is_visitor = role.lower() == "visitor"
    row = {
        "identity_id": identity_id,
        "name": name,
        "role": role,
        "authorized": authorized,
        "is_visitor": is_visitor,
    }
    try:
        client.table("registered_persons").upsert(row, on_conflict="identity_id").execute()
        return True
    except Exception:
        logger.exception("Failed to upsert person %s", identity_id)
        return False


def delete_person(identity_id: str) -> bool:
    """Remove a registered person from Supabase."""
    client = _get_client()
    if not client:
        return False
    try:
        client.table("registered_persons").delete().eq("identity_id", identity_id).execute()
        return True
    except Exception:
        logger.exception("Failed to delete person %s", identity_id)
        return False


def get_persons(role: Optional[str] = None, visitors_only: bool = False) -> list[dict]:
    """Fetch registered persons, optionally filtered."""
    client = _get_client()
    if not client:
        return []
    try:
        q = client.table("registered_persons").select("*")
        if role:
            q = q.eq("role", role)
        if visitors_only:
            q = q.eq("is_visitor", True)
        resp = q.order("registered_at", desc=True).execute()
        return resp.data or []
    except Exception:
        logger.exception("Failed to fetch persons")
        return []


# ── Visitor Log ────────────────────────────────────────────────────────────

def log_visitor_event(
    identity_id: str,
    person_name: str,
    action: str = "detected",
    feed_id: Optional[int] = None,
    zone_name: Optional[str] = None,
) -> bool:
    """Log a visitor detection / check-in / check-out event."""
    client = _get_client()
    if not client:
        return False

    row = {
        "identity_id": identity_id,
        "person_name": person_name,
        "action": action,
        "feed_id": feed_id,
        "zone_name": zone_name,
    }
    try:
        client.table("visitor_log").insert(row).execute()
        return True
    except Exception:
        logger.exception("Failed to log visitor event for %s", identity_id)
        return False


# ── Storage (GIF, PDF, images) ─────────────────────────────────────────────

def upload_file(bucket: str, path: str, file_bytes: bytes, content_type: str) -> Optional[str]:
    """Upload a file to Supabase Storage. Returns public URL or None."""
    client = _get_client()
    if not client:
        return None
    try:
        client.storage.from_(bucket).upload(
            path,
            file_bytes,
            file_options={"content-type": content_type, "upsert": "true"},
        )
        public_url = client.storage.from_(bucket).get_public_url(path)
        return public_url
    except Exception:
        logger.exception("Failed to upload to %s/%s", bucket, path)
        return None


def upload_recording(alert_id: str, gif_bytes: bytes) -> Optional[str]:
    """Upload a GIF recording to Supabase Storage."""
    return upload_file("recordings", f"{alert_id}.gif", gif_bytes, "image/gif")


def upload_report(alert_id: str, pdf_bytes: bytes) -> Optional[str]:
    """Upload a PDF report to Supabase Storage."""
    return upload_file("reports", f"{alert_id}.pdf", pdf_bytes, "application/pdf")


def upload_threat_image(alert_id: str, image_bytes: bytes) -> Optional[str]:
    """Upload a threat image to Supabase Storage."""
    return upload_file("threat-images", f"{alert_id}.jpg", image_bytes, "image/jpeg")


# ── Person Context for Escalation Agent ───────────────────────────────────

def get_person_context(person_name: str) -> dict:
    """Fetch profile + incident history from Supabase for the escalation agent.

    Returns a dict with:
      - profile: registered_persons row (or None if unknown)
      - prior_incidents: list of past security_incidents involving this person
      - visitor_events: recent visitor_log entries (if any)
    """
    result: dict = {"profile": None, "prior_incidents": [], "visitor_events": []}
    client = _get_client()
    if not client:
        return result

    # 1. Look up registered profile
    try:
        resp = (
            client.table("registered_persons")
            .select("*")
            .eq("name", person_name)
            .limit(1)
            .execute()
        )
        if resp.data:
            result["profile"] = resp.data[0]
    except Exception:
        logger.debug("Supabase profile lookup failed for %s", person_name)

    # 2. Prior incidents involving this person
    try:
        resp = (
            client.table("security_incidents")
            .select("alert_id, timestamp, alert_type, zone_name, escalation_level, resolution")
            .eq("person_name", person_name)
            .order("timestamp", desc=True)
            .limit(10)
            .execute()
        )
        result["prior_incidents"] = resp.data or []
    except Exception:
        logger.debug("Supabase incident history lookup failed for %s", person_name)

    # 3. Visitor log (if they were ever checked in as a visitor)
    try:
        resp = (
            client.table("visitor_log")
            .select("*")
            .eq("person_name", person_name)
            .order("event_time", desc=True)
            .limit(5)
            .execute()
        )
        result["visitor_events"] = resp.data or []
    except Exception:
        logger.debug("Supabase visitor log lookup failed for %s", person_name)

    return result
