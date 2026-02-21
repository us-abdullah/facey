"""
Door detection using YOLOv8 (doors.pt from YOLOv8-Door-detection repo or fallback).
Significant door movement = large pixel change in door ROI (open/close), not bbox jitter.
"""
from __future__ import annotations

import io
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

# Pre-trained door model (YOLOv8 door detection for visually impaired)
DOORS_PT_URL = "https://github.com/sayedmohamedscu/YOLOv8-Door-detection-for-visually-impaired-people/raw/main/doors.pt"

# In-memory state: last door bbox and last door crop (gray) per feed_id for frame-diff
_last_door_bbox: dict[int, list[float] | None] = {}
_last_door_crop_gray: dict[int, np.ndarray | None] = {}  # resized fixed size for diff
_last_recognition: dict[int, dict] = {}  # feed_id -> { detections, timestamp }

# Significant movement = mean abs diff in door ROI above this (0-1). Door open/close changes a lot.
_DOOR_DIFF_THRESHOLD = 0.12
_DOOR_CROP_SIZE = 64


def _is_role_authorized(role: str | None, allowed_roles: list[str]) -> bool:
    """C-Level (and legacy Admin) can open any door."""
    if not role:
        return False
    if role.strip() in ("C-Level", "Admin"):
        return True
    return role.strip() in allowed_roles


def _get_model_path() -> Path:
    """Path to doors.pt in data/models. Downloads from repo if missing."""
    base = Path(__file__).resolve().parent.parent
    models_dir = base / "data" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    pt = models_dir / "doors.pt"
    if pt.exists():
        return pt
    try:
        urllib.request.urlretrieve(DOORS_PT_URL, pt)
    except Exception:
        pass
    return pt


def _load_model():
    """Lazy-load YOLO model. Prefer doors.pt (downloaded if needed) else yolov8n.pt."""
    try:
        from ultralytics import YOLO
    except ImportError as e:
        raise RuntimeError("Install ultralytics: pip install ultralytics") from e
    pt = _get_model_path()
    if pt.exists():
        return YOLO(str(pt))
    return YOLO("yolov8n.pt")  # fallback: no door class but runs


_model = None
_model_error: str | None = None  # set if load failed, so we don't keep retrying


def get_door_model():
    """Return YOLO model or None if unavailable (caller should handle)."""
    global _model, _model_error
    if _model is not None:
        return _model
    if _model_error is not None:
        return None
    try:
        _model = _load_model()
        return _model
    except Exception as e:
        _model_error = str(e)
        return None


def _image_to_bgr(image_bytes: bytes) -> np.ndarray:
    import cv2
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def _bbox_iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a[0], a[1], a[2], a[3]
    bx1, by1, bx2, by2 = b[0], b[1], b[2], b[3]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / (area_a + area_b - inter) if (area_a + area_b - inter) > 0 else 0.0


def _bbox_center(bbox: list[float]) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def _resolve_door_config(feed_id: int, door_config: dict | None, areas: list[dict]) -> tuple[str | None, list, int | None]:
    """Return (area_name, allowed_roles, face_feed_id). Prefer door_config (floor plan point) if provided."""
    if door_config is not None:
        return (
            door_config.get("name"),
            list(door_config.get("allowed_roles") or []),
            feed_id,  # same feed does face + door
        )
    area = next((a for a in areas if a.get("door_feed_id") == feed_id), None)
    if area is None:
        return None, [], None
    return (
        area.get("name"),
        list(area.get("allowed_roles") or []),
        area.get("face_feed_id"),
    )


def _safe_fallback(feed_id: int, door_config: dict | None, areas: list[dict], hint: str | None = None) -> dict:
    """Return response when door model is unavailable or inference fails."""
    area_name, allowed_roles, face_feed_id = _resolve_door_config(feed_id, door_config, areas)
    last_person = None
    allowed = True
    if face_feed_id is not None:
        rec = _last_recognition.get(face_feed_id)
        if rec and rec.get("detections"):
            d = rec["detections"][0]
            last_person = {
                "name": d.get("name") or "Unknown",
                "role": d.get("role") or "Visitor",
                "identity_id": d.get("identity_id"),
            }
            role = (last_person.get("role") or "Visitor").strip()
            allowed = _is_role_authorized(role, allowed_roles)
    return {
        "doors": [],
        "movement_detected": False,
        "area_name": area_name,
        "last_person": last_person,
        "allowed": allowed,
        "alert": False,
        "hint": hint or "Door detector unavailable. Run: pip install ultralytics",
    }


def detect_doors(image_bytes: bytes, feed_id: int, areas: list[dict], door_config: dict | None = None) -> dict:
    """
    Run door detection on image; significant movement = frame-diff in door ROI (open/close).
    Permissions from door_config (floor plan point) if set, else from areas. Same feed_id can be
    used for both face and door (one camera); last_person from _last_recognition[feed_id].
    Returns dict for DoorDetectResponse. On any error returns safe fallback (no 500).
    """
    try:
        bgr = _image_to_bgr(image_bytes)
    except Exception:
        return _safe_fallback(feed_id, door_config, areas, hint="Could not decode image")
    h, w = bgr.shape[:2]
    diag = (w * w + h * h) ** 0.5

    model = get_door_model()
    if model is None:
        return _safe_fallback(feed_id, door_config, areas, hint="Door detector not loaded. Run: pip install ultralytics")

    try:
        results = model.predict(bgr, conf=0.12, verbose=False)
    except Exception:
        return _safe_fallback(feed_id, door_config, areas, hint="Door detection failed. Run: pip install ultralytics")

    doors = []
    for r in results:
        if r.boxes is None:
            continue
        for box in r.boxes:
            try:
                xyxy = box.xyxy[0].cpu().numpy().tolist()
                doors.append({"bbox": [float(x) for x in xyxy]})
            except Exception:
                continue

    # Pick largest door bbox for movement (significant = pixel change in door ROI, not bbox jitter)
    current_bbox = None
    if doors:
        doors.sort(key=lambda d: (d["bbox"][2] - d["bbox"][0]) * (d["bbox"][3] - d["bbox"][1]), reverse=True)
        current_bbox = doors[0]["bbox"]

    import cv2
    prev_bbox = _last_door_bbox.get(feed_id)
    prev_crop = _last_door_crop_gray.get(feed_id)
    movement_detected = False

    if current_bbox is not None:
        x1, y1, x2, y2 = [int(round(x)) for x in current_bbox]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 > x1 and y2 > y1:
            door_roi = bgr[y1:y2, x1:x2]
            gray = cv2.cvtColor(door_roi, cv2.COLOR_BGR2GRAY)
            crop_small = cv2.resize(gray, (_DOOR_CROP_SIZE, _DOOR_CROP_SIZE))
            crop_small = crop_small.astype(np.float32) / 255.0

            if prev_crop is not None and prev_bbox is not None:
                # Same door (overlap): significant movement = high pixel diff (door opening/closing)
                iou = _bbox_iou(current_bbox, prev_bbox)
                if iou >= 0.3:
                    diff = np.abs(crop_small - prev_crop)
                    mean_diff = float(np.mean(diff))
                    if mean_diff >= _DOOR_DIFF_THRESHOLD:
                        movement_detected = True
            else:
                movement_detected = True  # first time seeing door

            _last_door_crop_gray[feed_id] = crop_small
        else:
            _last_door_crop_gray[feed_id] = None
        _last_door_bbox[feed_id] = current_bbox
    else:
        if prev_bbox is not None:
            movement_detected = True  # door disappeared
        _last_door_bbox[feed_id] = None
        _last_door_crop_gray[feed_id] = None

    try:
        area_name, allowed_roles, face_feed_id = _resolve_door_config(feed_id, door_config, areas)
        last_person = None
        allowed = True
        alert = False
        if face_feed_id is not None:
            rec = _last_recognition.get(face_feed_id)
            if rec and rec.get("detections"):
                d = rec["detections"][0]
                last_person = {
                    "name": d.get("name") or "Unknown",
                    "role": d.get("role") or "Visitor",
                    "identity_id": d.get("identity_id"),
                }
                role = (last_person.get("role") or "Visitor").strip()
                allowed = _is_role_authorized(role, allowed_roles)
                if movement_detected and not allowed:
                    alert = True

        return {
            "doors": doors,
            "movement_detected": movement_detected,
            "area_name": area_name,
            "last_person": last_person,
            "allowed": allowed,
            "alert": alert,
            "hint": "No door detected. Point camera at the door. Run: pip install ultralytics" if not doors else None,
        }
    except Exception:
        return _safe_fallback(feed_id, door_config, areas)


def set_last_recognition(feed_id: int, detections: list[dict]) -> None:
    """Store last face recognition result for a feed (called from recognize endpoint)."""
    import time
    _last_recognition[feed_id] = {"detections": detections, "timestamp": time.time()}
