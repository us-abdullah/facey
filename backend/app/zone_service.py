"""
Restricted zone detection service – Feature 2.

Workflow per frame:
  1. Detect persons using YOLOv8n (COCO general model, class 0 = person).
  2. For each active zone on this feed:
     - "polygon" zones: fire alert if a person's feet land inside the polygon.
     - "line" zones   : fire alert when a person crosses from one side of the line to the other.
  3. Caller (main.py) decides whether to log unauthorized crossings to security_service.

Person-tracking uses a simple per-frame index (p0, p1 …). This is stable enough for line-side
tracking between consecutive frames at 400 ms intervals when there are few people.
"""
from __future__ import annotations

import io
import time
from pathlib import Path

import numpy as np
from PIL import Image

# ---------------------------------------------------------------------------
# Per-feed state for line-crossing detection
# {feed_id: {zone_id: {track_key: "A" | "B"}}}
# ---------------------------------------------------------------------------
_person_sides: dict[int, dict[str, dict[str, str]]] = {}

# ---------------------------------------------------------------------------
# Alert log-cooldown  (seconds) – prevents flooding the log when a person
# stands still inside a zone or paces back and forth across a line.
# ---------------------------------------------------------------------------
_ALERT_COOLDOWN = 15.0
_last_alert_log: dict[str, float] = {}  # key = f"{feed_id}:{zone_id}"


def _is_role_authorized(role: str | None, auth_roles: list[str]) -> bool:
    """C-Level (and legacy Admin) bypass all zone restrictions."""
    if not role:
        return False
    if role.strip() in ("C-Level", "Admin"):
        return True
    return role.strip() in auth_roles


# ---------------------------------------------------------------------------
# YOLOv8n model (general COCO) – lazy load
# ---------------------------------------------------------------------------
_model = None
_model_error: str | None = None


def _load_person_model():
    try:
        from ultralytics import YOLO
    except ImportError as e:
        raise RuntimeError("pip install ultralytics") from e
    return YOLO("yolov8n.pt")


def get_person_model():
    global _model, _model_error
    if _model is not None:
        return _model
    if _model_error is not None:
        return None
    try:
        _model = _load_person_model()
        return _model
    except Exception as e:
        _model_error = str(e)
        return None


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def _to_bgr(image_bytes: bytes) -> np.ndarray:
    import cv2
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def _point_in_polygon(px: float, py: float, polygon: list[list[float]]) -> bool:
    """Ray-casting algorithm. polygon = [[x, y], ...] in normalized 0-1 coords."""
    if len(polygon) < 3:
        return False
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py)) and (
            px < (xj - xi) * (py - yi) / ((yj - yi) if yj != yi else 1e-10) + xi
        ):
            inside = not inside
        j = i
    return inside


def _line_side(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Cross-product sign: positive on one side, negative on the other."""
    return (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)


# ---------------------------------------------------------------------------
# Person detection
# ---------------------------------------------------------------------------

def detect_persons(image_bytes: bytes) -> list[dict]:
    """
    Run YOLOv8n on image and return person detections.
    Returns list of:
      { bbox:[x1,y1,x2,y2], feet:[cx,by], center:[cx,cy], conf:float }
    All values are in pixel coordinates.
    """
    model = get_person_model()
    if model is None:
        return []
    try:
        bgr = _to_bgr(image_bytes)
    except Exception:
        return []
    try:
        results = model.predict(bgr, conf=0.50, classes=[0], verbose=False)
    except Exception:
        return []
    persons = []
    for r in results:
        if r.boxes is None:
            continue
        for box in r.boxes:
            try:
                xyxy = box.xyxy[0].cpu().numpy().tolist()
                conf = float(box.conf[0].cpu().numpy())
                x1, y1, x2, y2 = xyxy
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                by = y2  # bottom of bounding box ≈ feet position
                persons.append({
                    "bbox": [float(v) for v in xyxy],
                    "feet": [cx, by],
                    "center": [cx, cy],
                    "conf": conf,
                })
            except Exception:
                continue
    return persons


# ---------------------------------------------------------------------------
# Zone crossing check
# ---------------------------------------------------------------------------

def check_zones(
    image_bytes: bytes,
    feed_id: int,
    zones: list[dict],
    faces: list[dict] | None = None,
) -> list[dict]:
    """
    Detect persons in the frame and check each active zone for violations.

    Args:
        image_bytes: Raw image bytes for this frame.
        feed_id: Camera feed index (used for per-feed side-tracking state).
        zones: Active camera zones for this feed (from camera_zones_store).
        faces: Optional face detections to correlate identity with zone violations.

    Returns:
        List of zone_alert dicts. Includes both authorized and unauthorized alerts
        so the frontend can render them; the caller filters unauthorized ones for logging.

    Zone alert dict schema:
        zone_id, zone_name, zone_type, alert_type ("zone_presence"|"line_crossing"),
        person_bbox [x1,y1,x2,y2 pixels], person_feet_n [nx,ny normalized],
        person_name, person_role, authorized (bool)
    """
    if not zones:
        return []

    try:
        arr = _to_bgr(image_bytes)
    except Exception:
        return []

    h, w = arr.shape[:2]
    if w == 0 or h == 0:
        return []

    persons = detect_persons(image_bytes)
    if not persons:
        # Clean stale side-tracking for this feed when no one is visible
        if feed_id in _person_sides:
            _person_sides[feed_id] = {}
        return []

    # Normalize feet/center to 0-1
    for p in persons:
        p["feet_n"] = [p["feet"][0] / w, p["feet"][1] / h]
        p["center_n"] = [p["center"][0] / w, p["center"][1] / h]

    # ---------------------------------------------------------------------------
    # Match face detections to persons by spatial overlap (face is upper portion
    # of the person bbox). Returns (name, role, authorized) or (None, None, None).
    # ---------------------------------------------------------------------------
    def face_for_person(pbbox: list[float]):
        if not faces:
            return None, None, None
        px1, py1, px2, py2 = pbbox
        best_ov, best_f = 0.0, None
        for f in faces:
            fx1, fy1, fx2, fy2 = f.get("bbox", [0, 0, 0, 0])
            iw = min(fx2, px2) - max(fx1, px1)
            ih = min(fy2, py2) - max(fy1, py1)
            if iw > 0 and ih > 0:
                fa = (fx2 - fx1) * (fy2 - fy1)
                ov = (iw * ih) / fa if fa > 0 else 0.0
                if ov > best_ov:
                    best_ov = ov
                    best_f = f
        if best_f and best_ov > 0.25:
            return best_f.get("name"), best_f.get("role"), best_f.get("authorized")
        return None, None, None

    # ---------------------------------------------------------------------------
    # Per-feed side-tracking dict
    # ---------------------------------------------------------------------------
    if feed_id not in _person_sides:
        _person_sides[feed_id] = {}

    alerts: list[dict] = []

    for zone in zones:
        if not zone.get("active", True):
            continue

        zone_id = zone.get("id", "")
        zone_type = zone.get("zone_type", "polygon")
        points = zone.get("points", [])
        zone_name = zone.get("name", "Restricted Zone")
        auth_roles = zone.get("authorized_roles", [])

        if zone_id not in _person_sides[feed_id]:
            _person_sides[feed_id][zone_id] = {}

        current_person_keys: set[str] = set()

        for i, person in enumerate(persons):
            track_key = f"p{i}"
            current_person_keys.add(track_key)
            fx, fy = person["feet_n"]

            name, role, face_auth = face_for_person(person["bbox"])
            # C-Level/Admin bypass all zones; others checked against auth_roles
            authorized = _is_role_authorized(role, auth_roles)

            # ------------------------------------------------------------------
            # Polygon zone: presence detection
            # Requires ALL FOUR corners of the person bbox to be inside the
            # polygon so that merely clipping an edge doesn't trigger an alert.
            # ------------------------------------------------------------------
            if zone_type == "polygon" and len(points) >= 3:
                bx1, by1, bx2, by2 = person["bbox"]
                corners_n = [
                    (bx1 / w, by1 / h),  # top-left
                    (bx2 / w, by1 / h),  # top-right
                    (bx1 / w, by2 / h),  # bottom-left
                    (bx2 / w, by2 / h),  # bottom-right
                ]
                if all(_point_in_polygon(cx, cy, points) for cx, cy in corners_n):
                    alerts.append({
                        "zone_id": zone_id,
                        "zone_name": zone_name,
                        "zone_type": zone_type,
                        "alert_type": "zone_presence",
                        "person_bbox": person["bbox"],
                        "person_feet_n": person["feet_n"],
                        "person_name": name or "Unknown",
                        "person_role": role,
                        "authorized": authorized,
                    })

            # ------------------------------------------------------------------
            # Line zone: crossing detection
            # ------------------------------------------------------------------
            elif zone_type == "line" and len(points) >= 2:
                x1, y1 = points[0]
                x2, y2 = points[1]
                side_val = _line_side(fx, fy, x1, y1, x2, y2)
                current_side = "A" if side_val >= 0 else "B"

                prev_side = _person_sides[feed_id][zone_id].get(track_key)
                _person_sides[feed_id][zone_id][track_key] = current_side

                if prev_side is not None and prev_side != current_side:
                    # Side changed → crossing detected
                    alerts.append({
                        "zone_id": zone_id,
                        "zone_name": zone_name,
                        "zone_type": zone_type,
                        "alert_type": "line_crossing",
                        "person_bbox": person["bbox"],
                        "person_feet_n": person["feet_n"],
                        "person_name": name or "Unknown",
                        "person_role": role,
                        "authorized": authorized,
                    })

        # Purge stale tracking for persons no longer visible
        for k in list(_person_sides[feed_id].get(zone_id, {}).keys()):
            if k not in current_person_keys:
                del _person_sides[feed_id][zone_id][k]

    return alerts


def should_log_alert(feed_id: int, zone_id: str) -> bool:
    """
    Cooldown gate: return True (and reset timer) only if enough time has passed
    since the last logged alert for this (feed, zone) pair.
    Prevents flooding the alert log when a person stands in a zone for a long time.
    """
    key = f"{feed_id}:{zone_id}"
    now = time.time()
    if now - _last_alert_log.get(key, 0.0) >= _ALERT_COOLDOWN:
        _last_alert_log[key] = now
        return True
    return False
