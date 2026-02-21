"""
FastAPI backend: face registration, recognition, door detection, zone enforcement,
and security alert logging.

Feature 1 – Unauthorized door access:
    When a door moves AND the last recognized face is unauthorized, an alert is fired
    and logged to data/security_alerts.json.

Feature 2 – Restricted zone enforcement:
    Camera-view zones (polygons or boundary lines) are drawn by the operator.
    On every analysis frame, YOLOv8n detects persons and checks whether they violate
    any active zone for that feed.  Unauthorized violations are logged.
"""
import io
import logging
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

from app.camera_zones_store import (
    add_camera_zone,
    delete_camera_zone,
    get_zones_for_feed,
    load_camera_zones,
    update_camera_zone,
)
from app.door_areas_store import load_door_areas, save_door_areas
from app.door_service import detect_doors, set_last_recognition
from app.face_service import FaceService
from app.floorplan_store import (
    add_door,
    add_zone,
    delete_door,
    delete_zone,
    get_door_by_feed_id,
    get_floorplan_path,
    has_floorplan,
    load_doors,
    load_zones,
    save_floorplan_image,
    update_door,
    update_zone,
)
from app.schemas import (
    AlertsListResponse,
    CameraZone,
    CameraZonesListResponse,
    CreateCameraZoneBody,
    CreateDoorBody,
    CreateRoleBody,
    CreateZoneBody,
    DoorAreaItem,
    DoorAreasResponse,
    DoorAreaUpdateBody,
    DoorDetectResponse,
    DoorItem,
    DoorsListResponse,
    FaceListItem,
    FacesListResponse,
    FeedAnalyzeResponse,
    RecognizeResponse,
    RegisterResponse,
    RolesListResponse,
    SecurityAlert,
    UpdateCameraZoneBody,
    UpdateDoorBody,
    UpdateFaceBody,
    UpdateZoneBody,
    ZoneItem,
    ZonesListResponse,
)
from app.security_service import (
    acknowledge_alert,
    clear_alerts,
    get_alerts,
    log_alert,
)
from app.zone_service import check_zones, detect_persons, should_log_alert
from app import body_tracker

app = FastAPI(title="Hof Capital Inspection API", version="0.1.0")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    """Log unhandled exceptions and return JSON so client never gets empty 500."""
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_data_dir = Path(__file__).resolve().parent.parent / "data"
_data_dir.mkdir(parents=True, exist_ok=True)
_face_service: FaceService | None = None

# ---------------------------------------------------------------------------
# Frame buffer – keeps last ~3 s of frames per feed for violation recordings
# ---------------------------------------------------------------------------
_FRAME_BUFFER_MAX = 8           # 8 × 400 ms ≈ 3.2 s
_frame_buffers: dict[int, list[bytes]] = {}


def _buffer_frame(feed_id: int, image_bytes: bytes) -> None:
    buf = _frame_buffers.setdefault(feed_id, [])
    buf.append(image_bytes)
    if len(buf) > _FRAME_BUFFER_MAX:
        buf.pop(0)


def _save_recording(alert_id: str, feed_id: int) -> str | None:
    """Save the last ~3 s of frames for feed_id as an animated GIF.
    Returns the URL path or None if no frames are available."""
    try:
        from PIL import Image as _Img
        frames = _frame_buffers.get(feed_id, [])
        if not frames:
            return None
        rec_dir = _data_dir / "recordings"
        rec_dir.mkdir(parents=True, exist_ok=True)
        path = rec_dir / f"{alert_id}.gif"
        imgs: list[_Img.Image] = []
        for fb in frames:
            try:
                img = _Img.open(io.BytesIO(fb)).convert("RGB")
                img.thumbnail((320, 240), _Img.LANCZOS)
                imgs.append(img)
            except Exception:
                continue
        if not imgs:
            return None
        imgs[0].save(
            path,
            save_all=True,
            append_images=imgs[1:],
            loop=0,
            duration=400,
            optimize=False,
        )
        return f"/api/security/recordings/{alert_id}"
    except Exception as e:
        logger.warning("Could not save recording: %s", e)
        return None


def get_face_service() -> FaceService:
    global _face_service
    if _face_service is None:
        _face_service = FaceService(data_dir=_data_dir)
    return _face_service


# ---------------------------------------------------------------------------
# Feature 1 helper – door alert logging with per-feed cooldown
# ---------------------------------------------------------------------------
_door_alert_cooldown: dict[int, float] = {}
_DOOR_ALERT_COOLDOWN = 15.0  # seconds between logged alerts for the same feed


def _maybe_log_door_alert(feed_id: int, door_result: dict) -> None:
    """Log an unauthorized-door-access alert if the cooldown has elapsed."""
    if not door_result.get("alert"):
        return
    now = time.time()
    if now - _door_alert_cooldown.get(feed_id, 0.0) < _DOOR_ALERT_COOLDOWN:
        return
    _door_alert_cooldown[feed_id] = now
    last = door_result.get("last_person") or {}
    alert = log_alert(
        _data_dir,
        alert_type="unauthorized_door_access",
        feed_id=feed_id,
        person_name=last.get("name", "Unknown"),
        person_role=last.get("role"),
        authorized=False,
        zone_name=door_result.get("area_name"),
        details=(
            f"Unauthorized access attempt at '{door_result.get('area_name', 'door')}' – "
            "door movement detected with unrecognized or unauthorized face"
        ),
    )
    rec_url = _save_recording(alert["alert_id"], feed_id)
    if rec_url:
        from app.security_service import _load as _sload, _save as _ssave
        saved = _sload(_data_dir)
        for a in saved:
            if a.get("alert_id") == alert["alert_id"]:
                a["recording_url"] = rec_url
                break
        _ssave(_data_dir, saved)


# ---------------------------------------------------------------------------
# Feature 2 helper – zone check + logging
# ---------------------------------------------------------------------------

def _run_zone_check(
    contents: bytes,
    feed_id: int,
    faces: list[dict] | None = None,
) -> list[dict]:
    """
    Run zone crossing/presence check for this feed's active zones.
    Logs unauthorized alerts (with cooldown) to the security log.
    Returns the full list of zone_alert dicts for the API response.
    """
    zones = get_zones_for_feed(_data_dir, feed_id)
    if not zones:
        return []

    zone_alerts = check_zones(contents, feed_id, zones, faces)

    for za in zone_alerts:
        if not za.get("authorized") and should_log_alert(feed_id, za.get("zone_id", "")):
            atype = za.get("alert_type", "zone_presence")
            zname = za.get("zone_name", "unknown zone")
            suffix = " – boundary line crossed" if atype == "line_crossing" else ""
            alert = log_alert(
                _data_dir,
                alert_type=atype,
                feed_id=feed_id,
                person_name=za.get("person_name", "Unknown"),
                person_role=za.get("person_role"),
                authorized=False,
                zone_name=za.get("zone_name"),
                details=f"Unauthorized person detected in restricted zone '{zname}'{suffix}",
            )
            rec_url = _save_recording(alert["alert_id"], feed_id)
            if rec_url:
                from app.security_service import _load as _sload, _save as _ssave
                saved = _sload(_data_dir)
                for a in saved:
                    if a.get("alert_id") == alert["alert_id"]:
                        a["recording_url"] = rec_url
                        break
                _ssave(_data_dir, saved)

    return zone_alerts


# ===========================================================================
# Face endpoints
# ===========================================================================

@app.post("/api/register", response_model=RegisterResponse)
async def register_face(
    name: str = Form(...),
    role: str = Form("Visitor"),
    file: UploadFile = File(...),
):
    """Register a face from an uploaded image. Uses first/largest face found."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    try:
        contents = await file.read()
    except Exception as e:
        logger.exception("Failed to read upload")
        raise HTTPException(400, f"Failed to read image: {e!s}")
    try:
        svc = get_face_service()
        identity_id, message = svc.register(contents, name, role=role or "Visitor")
        return RegisterResponse(identity_id=identity_id, name=name, message=message)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("Register failed")
        raise HTTPException(503, detail=f"Registration failed: {e!s}")


@app.post("/api/recognize", response_model=RecognizeResponse)
async def recognize_face(
    file: UploadFile = File(...),
    feed_id: int = Form(None),
):
    """Detect faces + check camera zones. feed_id required for zone enforcement."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    try:
        contents = await file.read()
    except Exception as e:
        logger.exception("Failed to read upload")
        raise HTTPException(400, f"Failed to read image: {e!s}")
    if feed_id is not None:
        _buffer_frame(int(feed_id), contents)

    try:
        svc = get_face_service()
        raw_detections = svc.recognize(contents)
        face_dicts = [d if isinstance(d, dict) else d.model_dump() for d in raw_detections]
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("Recognize failed")
        raise HTTPException(503, detail=f"Recognition failed: {e!s}")

    # Body tracking: detect person bboxes and lock identity to body so we keep
    # showing who someone is even when their face is no longer in frame.
    dicts = face_dicts
    if feed_id is not None:
        try:
            person_bboxes = [p["bbox"] for p in detect_persons(contents)]
            if person_bboxes:
                dicts = body_tracker.update(int(feed_id), person_bboxes, face_dicts)
        except Exception as e:
            logger.warning("Body tracking failed: %s", e)

    if feed_id is not None:
        set_last_recognition(int(feed_id), dicts)

    zone_alerts: list[dict] = []
    try:
        if feed_id is not None:
            zone_alerts = _run_zone_check(contents, int(feed_id), faces=dicts)
    except Exception as e:
        logger.warning("Zone check failed: %s", e)

    return RecognizeResponse(detections=dicts, zone_alerts=zone_alerts)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/faces", response_model=FacesListResponse)
async def list_faces():
    try:
        svc = get_face_service()
        raw = svc.list_faces()
        faces = [FaceListItem(**f) for f in raw]
        return FacesListResponse(faces=faces)
    except Exception:
        return FacesListResponse(faces=[])


@app.patch("/api/faces/{identity_id}")
async def update_face(identity_id: str, body: UpdateFaceBody):
    svc = get_face_service()
    try:
        svc.update_face(identity_id, name=body.name, role=body.role, authorized=body.authorized)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.delete("/api/faces/{identity_id}")
async def delete_face(identity_id: str):
    svc = get_face_service()
    try:
        svc.delete_face(identity_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(404, str(e))


# ===========================================================================
# Role endpoints
# ===========================================================================

@app.get("/api/roles", response_model=RolesListResponse)
async def list_roles():
    try:
        svc = get_face_service()
        roles = svc.get_roles()
        return RolesListResponse(roles=roles if roles else ["Visitor", "Analyst", "C-Level"])
    except Exception:
        return RolesListResponse(roles=["Visitor", "Analyst", "C-Level"])


@app.post("/api/roles")
async def create_role(body: CreateRoleBody):
    svc = get_face_service()
    try:
        svc.add_role(body.name.strip())
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/roles/{role_name}")
async def delete_role(role_name: str):
    svc = get_face_service()
    try:
        svc.delete_role(role_name)
        return {"ok": True}
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(404, str(e))
        raise HTTPException(400, str(e))


# ===========================================================================
# Floor plan endpoints
# ===========================================================================

@app.post("/api/floorplan")
async def upload_floorplan(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    contents = await file.read()
    save_floorplan_image(_data_dir, contents)
    return {"ok": True}


@app.get("/api/floorplan/image")
async def get_floorplan_image():
    path = get_floorplan_path(_data_dir)
    if not path.exists():
        raise HTTPException(404, "No floor plan uploaded")
    return FileResponse(path, media_type="image/png")


@app.get("/api/floorplan")
async def get_floorplan_status():
    return {"has_floorplan": has_floorplan(_data_dir)}


@app.get("/api/floorplan/zones", response_model=ZonesListResponse)
async def list_floorplan_zones():
    zones = load_zones(_data_dir)
    return ZonesListResponse(zones=[ZoneItem(**z) for z in zones])


@app.post("/api/floorplan/zones", response_model=ZoneItem)
async def create_floorplan_zone(body: CreateZoneBody):
    zone = add_zone(_data_dir, body.model_dump())
    return ZoneItem(**zone)


@app.patch("/api/floorplan/zones/{zone_id}")
async def update_floorplan_zone(zone_id: str, body: UpdateZoneBody):
    updates = body.model_dump(exclude_unset=True)
    updated = update_zone(_data_dir, zone_id, updates)
    if updated is None:
        raise HTTPException(404, "Zone not found")
    return {"ok": True}


@app.delete("/api/floorplan/zones/{zone_id}")
async def delete_floorplan_zone(zone_id: str):
    if not delete_zone(_data_dir, zone_id):
        raise HTTPException(404, "Zone not found")
    return {"ok": True}


@app.get("/api/floorplan/doors", response_model=DoorsListResponse)
async def list_floorplan_doors():
    doors = load_doors(_data_dir)
    return DoorsListResponse(doors=[DoorItem(**d) for d in doors])


@app.post("/api/floorplan/doors", response_model=DoorItem)
async def create_floorplan_door(body: CreateDoorBody):
    door = add_door(_data_dir, body.model_dump())
    return DoorItem(**door)


@app.patch("/api/floorplan/doors/{door_id}")
async def update_floorplan_door(door_id: str, body: UpdateDoorBody):
    updates = body.model_dump(exclude_unset=True)
    updated = update_door(_data_dir, door_id, updates)
    if updated is None:
        raise HTTPException(404, "Door not found")
    return {"ok": True}


@app.delete("/api/floorplan/doors/{door_id}")
async def delete_floorplan_door(door_id: str):
    if not delete_door(_data_dir, door_id):
        raise HTTPException(404, "Door not found")
    return {"ok": True}


# ===========================================================================
# Door access endpoints
# ===========================================================================

_DEFAULT_DOOR_AREAS = [
    {"id": "office1", "name": "Office 1", "face_feed_id": 0, "door_feed_id": 1, "allowed_roles": ["C-Level"]},
    {"id": "office2", "name": "Office 2", "face_feed_id": 2, "door_feed_id": 3, "allowed_roles": ["Analyst", "C-Level"]},
]


@app.get("/api/door/areas", response_model=DoorAreasResponse)
async def get_door_areas():
    try:
        areas = load_door_areas(_data_dir)
        out = []
        for a in areas:
            try:
                out.append(DoorAreaItem(**a))
            except Exception:
                pass
        if not out:
            out = [DoorAreaItem(**a) for a in _DEFAULT_DOOR_AREAS]
        return DoorAreasResponse(areas=out)
    except Exception:
        return DoorAreasResponse(areas=[DoorAreaItem(**a) for a in _DEFAULT_DOOR_AREAS])


@app.put("/api/door/areas", response_model=DoorAreasResponse)
async def update_door_areas(body: DoorAreaUpdateBody):
    areas = [a.model_dump() for a in body.areas]
    for a in areas:
        if "id" not in a or not a["id"]:
            a["id"] = a.get("name", "").lower().replace(" ", "") or "area"
    save_door_areas(_data_dir, areas)
    return DoorAreasResponse(areas=[DoorAreaItem(**a) for a in areas])


@app.post("/api/door/detect", response_model=DoorDetectResponse)
async def door_detect(
    file: UploadFile = File(...),
    feed_id: int = Form(0),
):
    """Run door detection + zone check on image. Feature 1 + Feature 2."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    try:
        contents = await file.read()
    except Exception as e:
        raise HTTPException(400, f"Failed to read file: {e}") from e

    _buffer_frame(int(feed_id), contents)

    areas = load_door_areas(_data_dir)
    door_config = get_door_by_feed_id(_data_dir, int(feed_id))

    try:
        result = detect_doors(contents, int(feed_id), areas, door_config=door_config)
    except Exception:
        from app.door_service import _safe_fallback
        result = _safe_fallback(int(feed_id), door_config, areas)

    # Feature 1: log unauthorized door alert
    _maybe_log_door_alert(int(feed_id), result)

    # Feature 2: zone check (no face detections available in this endpoint)
    zone_alerts = _run_zone_check(contents, int(feed_id), faces=None)

    return DoorDetectResponse(**result, zone_alerts=zone_alerts)


@app.post("/api/feed/analyze", response_model=FeedAnalyzeResponse)
async def feed_analyze(
    file: UploadFile = File(...),
    feed_id: int = Form(0),
):
    """Combined face + door analysis on same frame. Feature 1 + Feature 2."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    try:
        contents = await file.read()
    except Exception as e:
        raise HTTPException(400, f"Failed to read file: {e}") from e

    _buffer_frame(int(feed_id), contents)

    svc = get_face_service()
    areas = load_door_areas(_data_dir)
    door_config = get_door_by_feed_id(_data_dir, int(feed_id))

    try:
        raw_detections = svc.recognize(contents)
        face_dicts = [d if isinstance(d, dict) else d.model_dump() for d in raw_detections]
    except ValueError:
        face_dicts = []

    # Body tracking
    detections_dict = face_dicts
    try:
        person_bboxes = [p["bbox"] for p in detect_persons(contents)]
        if person_bboxes:
            detections_dict = body_tracker.update(int(feed_id), person_bboxes, face_dicts)
    except Exception as e:
        logger.warning("Body tracking failed: %s", e)

    set_last_recognition(int(feed_id), detections_dict)

    try:
        door_result = detect_doors(contents, int(feed_id), areas, door_config=door_config)
    except Exception:
        from app.door_service import _safe_fallback
        door_result = _safe_fallback(int(feed_id), door_config, areas)

    # Feature 1: log unauthorized door alert
    _maybe_log_door_alert(int(feed_id), door_result)

    # Feature 2: zone check with face context for identity correlation
    zone_alerts = _run_zone_check(contents, int(feed_id), faces=detections_dict)

    return FeedAnalyzeResponse(
        detections=detections_dict,
        doors=door_result.get("doors", []),
        movement_detected=door_result.get("movement_detected", False),
        area_name=door_result.get("area_name"),
        last_person=door_result.get("last_person"),
        allowed=door_result.get("allowed", True),
        alert=door_result.get("alert", False),
        hint=door_result.get("hint"),
        zone_alerts=zone_alerts,
    )


# ===========================================================================
# Security alerts endpoints  (Feature 1 + 2 log)
# ===========================================================================

@app.get("/api/security/alerts", response_model=AlertsListResponse)
async def list_security_alerts(limit: int = 200):
    """Return recent security alerts, newest first."""
    alerts = get_alerts(_data_dir, limit=limit)
    return AlertsListResponse(alerts=[SecurityAlert(**a) for a in alerts])


@app.delete("/api/security/alerts")
async def clear_security_alerts():
    """Delete all security alerts."""
    clear_alerts(_data_dir)
    return {"ok": True}


@app.post("/api/security/alerts/{alert_id}/acknowledge")
async def acknowledge_security_alert(alert_id: str):
    """Mark a single alert as acknowledged."""
    found = acknowledge_alert(_data_dir, alert_id)
    if not found:
        raise HTTPException(404, "Alert not found")
    return {"ok": True}


# ===========================================================================
# Camera-view zone endpoints  (Feature 2 zone management)
# ===========================================================================

@app.get("/api/camera-zones", response_model=CameraZonesListResponse)
async def list_camera_zones(feed_id: int | None = None):
    """List camera-view zones. Optionally filter by feed_id."""
    if feed_id is not None:
        zones = get_zones_for_feed(_data_dir, feed_id)
    else:
        zones = load_camera_zones(_data_dir)
    return CameraZonesListResponse(zones=[CameraZone(**z) for z in zones])


@app.post("/api/camera-zones", response_model=CameraZone)
async def create_camera_zone(body: CreateCameraZoneBody):
    """Create a new camera-view zone (polygon or boundary line)."""
    zone = add_camera_zone(_data_dir, body.model_dump())
    return CameraZone(**zone)


@app.patch("/api/camera-zones/{zone_id}", response_model=CameraZone)
async def update_camera_zone_endpoint(zone_id: str, body: UpdateCameraZoneBody):
    """Update a camera zone's properties."""
    updates = body.model_dump(exclude_unset=True)
    updated = update_camera_zone(_data_dir, zone_id, updates)
    if updated is None:
        raise HTTPException(404, "Camera zone not found")
    return CameraZone(**updated)


@app.delete("/api/camera-zones/{zone_id}")
async def delete_camera_zone_endpoint(zone_id: str):
    """Delete a camera zone."""
    if not delete_camera_zone(_data_dir, zone_id):
        raise HTTPException(404, "Camera zone not found")
    return {"ok": True}


# ===========================================================================
# Violation recordings
# ===========================================================================

@app.get("/api/security/recordings/{alert_id}")
async def get_recording(alert_id: str):
    """Serve the animated GIF recording attached to a security alert."""
    path = _data_dir / "recordings" / f"{alert_id}.gif"
    if not path.exists():
        raise HTTPException(404, "Recording not found")
    return FileResponse(str(path), media_type="image/gif")


# ===========================================================================
# Static frontend (production build)
# ===========================================================================

_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="static")
