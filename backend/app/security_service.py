"""
Security alert logging for:
  Feature 1: Unauthorized face + door open  (alert_type="unauthorized_door_access")
  Feature 2: Restricted zone crossing/presence (alert_type="line_crossing" | "zone_presence")

Alerts are persisted to data/security_alerts.json (up to 1000 entries, newest last).
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Optional


def _get_path(data_dir: Path) -> Path:
    return data_dir / "security_alerts.json"


def _load(data_dir: Path) -> list[dict]:
    p = _get_path(data_dir)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(data_dir: Path, alerts: list[dict]) -> None:
    p = _get_path(data_dir)
    p.write_text(json.dumps(alerts, indent=2, ensure_ascii=False), encoding="utf-8")


def log_alert(
    data_dir: Path,
    *,
    alert_type: str,
    feed_id: int,
    person_name: str = "Unknown",
    person_role: Optional[str] = None,
    authorized: bool = False,
    zone_name: Optional[str] = None,
    details: str = "",
    recording_url: Optional[str] = None,
) -> dict:
    """Append a new security alert to the persistent log. Returns the created alert dict."""
    alerts = _load(data_dir)
    alert = {
        "alert_id": str(uuid.uuid4()),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "alert_type": alert_type,
        "feed_id": feed_id,
        "person_name": person_name,
        "person_role": person_role,
        "authorized": authorized,
        "zone_name": zone_name,
        "details": details,
        "acknowledged": False,
        "recording_url": recording_url,
    }
    alerts.append(alert)
    # Cap at 1000 entries
    if len(alerts) > 1000:
        alerts = alerts[-1000:]
    _save(data_dir, alerts)
    return alert


def get_alerts(data_dir: Path, limit: int = 200) -> list[dict]:
    """Return most recent alerts, newest first."""
    alerts = _load(data_dir)
    return list(reversed(alerts[-limit:]))


def clear_alerts(data_dir: Path) -> None:
    """Delete all alerts."""
    _save(data_dir, [])


def acknowledge_alert(data_dir: Path, alert_id: str) -> bool:
    """Mark a single alert as acknowledged. Returns True if found."""
    alerts = _load(data_dir)
    for a in alerts:
        if a.get("alert_id") == alert_id:
            a["acknowledged"] = True
            _save(data_dir, alerts)
            return True
    return False
