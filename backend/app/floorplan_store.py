"""
Store floorplan image, zones (legacy), and doors (points). Image in data/floorplan.png.
Zones in data/floorplan_zones.json; doors in data/floorplan_doors.json.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path


def get_doors_path(data_dir: Path) -> Path:
    return Path(data_dir) / "floorplan_doors.json"


def load_doors(data_dir: Path) -> list[dict]:
    path = get_doors_path(data_dir)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_doors(data_dir: Path, doors: list[dict]) -> None:
    path = get_doors_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doors, indent=2), encoding="utf-8")


def add_door(data_dir: Path, door: dict) -> dict:
    doors = load_doors(data_dir)
    door_id = str(uuid.uuid4())
    door["id"] = door_id
    doors.append(door)
    save_doors(data_dir, doors)
    return door


def update_door(data_dir: Path, door_id: str, updates: dict) -> dict | None:
    doors = load_doors(data_dir)
    for i, d in enumerate(doors):
        if d.get("id") == door_id:
            doors[i] = {**d, **{k: v for k, v in updates.items() if v is not None}}
            save_doors(data_dir, doors)
            return doors[i]
    return None


def delete_door(data_dir: Path, door_id: str) -> bool:
    doors = load_doors(data_dir)
    new_doors = [d for d in doors if d.get("id") != door_id]
    if len(new_doors) == len(doors):
        return False
    save_doors(data_dir, new_doors)
    return True


def get_door_by_feed_id(data_dir: Path, feed_id: int) -> dict | None:
    """Return door config for the given camera feed_id (used for permissions)."""
    for d in load_doors(data_dir):
        if d.get("feed_id") is not None and int(d["feed_id"]) == int(feed_id):
            return d
    return None


def get_floorplan_path(data_dir: Path) -> Path:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "floorplan.png"


def get_zones_path(data_dir: Path) -> Path:
    return Path(data_dir) / "floorplan_zones.json"


def save_floorplan_image(data_dir: Path, contents: bytes) -> Path:
    path = get_floorplan_path(data_dir)
    path.write_bytes(contents)
    return path


def has_floorplan(data_dir: Path) -> bool:
    return get_floorplan_path(data_dir).exists()


def load_zones(data_dir: Path) -> list[dict]:
    path = get_zones_path(data_dir)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_zones(data_dir: Path, zones: list[dict]) -> None:
    path = get_zones_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(zones, indent=2), encoding="utf-8")


def add_zone(data_dir: Path, zone: dict) -> dict:
    zones = load_zones(data_dir)
    zone_id = str(uuid.uuid4())
    zone["id"] = zone_id
    zones.append(zone)
    save_zones(data_dir, zones)
    return zone


def update_zone(data_dir: Path, zone_id: str, updates: dict) -> dict | None:
    zones = load_zones(data_dir)
    for i, z in enumerate(zones):
        if z.get("id") == zone_id:
            zones[i] = {**z, **{k: v for k, v in updates.items() if v is not None}}
            save_zones(data_dir, zones)
            return zones[i]
    return None


def delete_zone(data_dir: Path, zone_id: str) -> bool:
    zones = load_zones(data_dir)
    new_zones = [z for z in zones if z.get("id") != zone_id]
    if len(new_zones) == len(zones):
        return False
    save_zones(data_dir, new_zones)
    return True
