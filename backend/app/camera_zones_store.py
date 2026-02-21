"""
Persistence for camera-view zones (drawn directly on live video feed, not the floor plan).

Zone types:
  "polygon" – closed shape; alert fires whenever a person's feet are inside
  "line"    – two-point boundary; alert fires when a person crosses from one side to the other

All coordinates are normalized 0-1 relative to the video frame dimensions.
Stored in data/camera_zones.json.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path


def _get_path(data_dir: Path) -> Path:
    return data_dir / "camera_zones.json"


def load_camera_zones(data_dir: Path) -> list[dict]:
    p = _get_path(data_dir)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(data_dir: Path, zones: list[dict]) -> None:
    p = _get_path(data_dir)
    p.write_text(json.dumps(zones, indent=2, ensure_ascii=False), encoding="utf-8")


def get_zones_for_feed(data_dir: Path, feed_id: int) -> list[dict]:
    """Return active zones for a specific camera feed."""
    return [
        z for z in load_camera_zones(data_dir)
        if z.get("feed_id") == feed_id and z.get("active", True)
    ]


def add_camera_zone(data_dir: Path, zone_data: dict) -> dict:
    zones = load_camera_zones(data_dir)
    zone = {
        "id": str(uuid.uuid4()),
        "feed_id": int(zone_data.get("feed_id", 0)),
        "name": zone_data.get("name", "Restricted Zone"),
        "zone_type": zone_data.get("zone_type", "polygon"),  # "polygon" | "line"
        "points": list(zone_data.get("points", [])),           # [[x,y], ...] normalized 0-1
        "authorized_roles": list(zone_data.get("authorized_roles", [])),
        "color": zone_data.get("color", "#ef4444"),
        "active": bool(zone_data.get("active", True)),
    }
    zones.append(zone)
    _save(data_dir, zones)
    return zone


def update_camera_zone(data_dir: Path, zone_id: str, updates: dict) -> dict | None:
    zones = load_camera_zones(data_dir)
    for z in zones:
        if z.get("id") == zone_id:
            for k, v in updates.items():
                if k != "id":
                    z[k] = v
            _save(data_dir, zones)
            return z
    return None


def delete_camera_zone(data_dir: Path, zone_id: str) -> bool:
    zones = load_camera_zones(data_dir)
    new_zones = [z for z in zones if z.get("id") != zone_id]
    if len(new_zones) == len(zones):
        return False
    _save(data_dir, new_zones)
    return True
