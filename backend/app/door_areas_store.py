"""
Store door access areas: name, face_feed_id, door_feed_id, allowed_roles.
Persisted in data/door_areas.json.
"""
from __future__ import annotations

import json
from pathlib import Path


def get_door_areas_path(data_dir: Path) -> Path:
    return Path(data_dir) / "door_areas.json"


def _default_areas() -> list[dict]:
    return [
        {"id": "office1", "name": "Office 1", "face_feed_id": 0, "door_feed_id": 1, "allowed_roles": ["Admin"]},
        {"id": "office2", "name": "Office 2", "face_feed_id": 2, "door_feed_id": 3, "allowed_roles": ["Admin", "Worker"]},
    ]


def load_door_areas(data_dir: Path) -> list[dict]:
    path = get_door_areas_path(data_dir)
    if not path.exists():
        return _default_areas()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_areas()
    if not isinstance(raw, list) or len(raw) == 0:
        return _default_areas()
    # Normalize so each item has id, name, face_feed_id (int), door_feed_id (int), allowed_roles (list)
    out = []
    for i, a in enumerate(raw):
        if not isinstance(a, dict):
            continue
        out.append({
            "id": str(a.get("id") or a.get("name", "area")).lower().replace(" ", "") or f"area{i}",
            "name": str(a.get("name") or f"Area {i + 1}"),
            "face_feed_id": int(a.get("face_feed_id", 0)) if a.get("face_feed_id") is not None else 0,
            "door_feed_id": int(a.get("door_feed_id", 1)) if a.get("door_feed_id") is not None else 1,
            "allowed_roles": list(a.get("allowed_roles") or []) if isinstance(a.get("allowed_roles"), list) else [],
        })
    return out if out else _default_areas()


def save_door_areas(data_dir: Path, areas: list[dict]) -> None:
    path = get_door_areas_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(areas, indent=2), encoding="utf-8")
