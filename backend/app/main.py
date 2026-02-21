"""
FastAPI backend: face registration, recognition, and known-face DB.
Serves API and (in production) static frontend.
"""
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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
    UpdateDoorBody,
    UpdateFaceBody,
    UpdateZoneBody,
    ZoneItem,
    ZonesListResponse,
)

app = FastAPI(title="Hof Capital Inspection API", version="0.1.0")

# Allow frontend (Vite dev or static) to call API. Permissive for dev so localhost/127.0.0.1 both work.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # e.g. http://localhost:5173, http://127.0.0.1:5173
    allow_credentials=False,  # must be False when allow_origins is "*"
    allow_methods=["*"],
    allow_headers=["*"],
)

# Face service (lazy init on first use)
_data_dir = Path(__file__).resolve().parent.parent / "data"
_data_dir.mkdir(parents=True, exist_ok=True)
_face_service: FaceService | None = None


def get_face_service() -> FaceService:
    global _face_service
    if _face_service is None:
        _face_service = FaceService(data_dir=_data_dir)
    return _face_service


@app.post("/api/register", response_model=RegisterResponse)
async def register_face(
    name: str = Form(...),
    role: str = Form("Visitor"),
    file: UploadFile = File(...),
):
    """Register a face from an uploaded image. Uses first/largest face found."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    contents = await file.read()
    svc = get_face_service()
    try:
        identity_id, message = svc.register(contents, name, role=role or "Visitor")
        return RegisterResponse(identity_id=identity_id, name=name, message=message)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/recognize", response_model=RecognizeResponse)
async def recognize_face(
    file: UploadFile = File(...),
    feed_id: int = Form(None),
):
    """Detect faces in image and return bboxes + identity + authorized flag. If feed_id is set, store result for door-access correlation."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    contents = await file.read()
    svc = get_face_service()
    try:
        detections = svc.recognize(contents)
        if feed_id is not None:
            # detections from face_service are already dicts
            set_last_recognition(feed_id, [d if isinstance(d, dict) else d.model_dump() for d in detections])
        return RecognizeResponse(detections=detections)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/faces", response_model=FacesListResponse)
async def list_faces():
    """List all registered faces (for manage UI)."""
    try:
        svc = get_face_service()
        raw = svc.list_faces()
        faces = [FaceListItem(**f) for f in raw]
        return FacesListResponse(faces=faces)
    except Exception:
        return FacesListResponse(faces=[])


@app.patch("/api/faces/{identity_id}")
async def update_face(identity_id: str, body: UpdateFaceBody):
    """Update name and/or authorized for a registered face."""
    svc = get_face_service()
    try:
        svc.update_face(identity_id, name=body.name, role=body.role, authorized=body.authorized)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.delete("/api/faces/{identity_id}")
async def delete_face(identity_id: str):
    """Remove a registered face."""
    svc = get_face_service()
    try:
        svc.delete_face(identity_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.get("/api/roles", response_model=RolesListResponse)
async def list_roles():
    """List all roles (for dropdowns and role management)."""
    try:
        svc = get_face_service()
        roles = svc.get_roles()
        return RolesListResponse(roles=roles if roles else ["Visitor", "Worker", "Admin"])
    except Exception:
        return RolesListResponse(roles=["Visitor", "Worker", "Admin"])


@app.post("/api/roles")
async def create_role(body: CreateRoleBody):
    """Create a new role."""
    svc = get_face_service()
    try:
        svc.add_role(body.name.strip())
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/roles/{role_name}")
async def delete_role(role_name: str):
    """Delete a role. Fails if any person has this role."""
    svc = get_face_service()
    try:
        svc.delete_role(role_name)
        return {"ok": True}
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(404, str(e))
        raise HTTPException(400, str(e))


# --- Floor plan ---
@app.post("/api/floorplan")
async def upload_floorplan(file: UploadFile = File(...)):
    """Upload floor plan image (PNG/JPEG). Replaces existing."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    contents = await file.read()
    save_floorplan_image(_data_dir, contents)
    return {"ok": True}


@app.get("/api/floorplan/image")
async def get_floorplan_image():
    """Return the floor plan image or 404."""
    path = get_floorplan_path(_data_dir)
    if not path.exists():
        raise HTTPException(404, "No floor plan uploaded")
    return FileResponse(path, media_type="image/png")


@app.get("/api/floorplan")
async def get_floorplan_status():
    """Return whether a floor plan exists (for UI)."""
    return {"has_floorplan": has_floorplan(_data_dir)}


@app.get("/api/floorplan/zones", response_model=ZonesListResponse)
async def list_floorplan_zones():
    """List all zones on the floor plan."""
    zones = load_zones(_data_dir)
    return ZonesListResponse(zones=[ZoneItem(**z) for z in zones])


@app.post("/api/floorplan/zones", response_model=ZoneItem)
async def create_floorplan_zone(body: CreateZoneBody):
    """Create a new zone (drawn shape with rules)."""
    zone = add_zone(_data_dir, body.model_dump())
    return ZoneItem(**zone)


@app.patch("/api/floorplan/zones/{zone_id}")
async def update_floorplan_zone(zone_id: str, body: UpdateZoneBody):
    """Update zone name, allowed_roles, restriction_level, or rules."""
    updates = body.model_dump(exclude_unset=True)
    updated = update_zone(_data_dir, zone_id, updates)
    if updated is None:
        raise HTTPException(404, "Zone not found")
    return {"ok": True}


@app.delete("/api/floorplan/zones/{zone_id}")
async def delete_floorplan_zone(zone_id: str):
    """Delete a zone."""
    if not delete_zone(_data_dir, zone_id):
        raise HTTPException(404, "Zone not found")
    return {"ok": True}


# --- Floor plan doors (points on map; one feed_id per door = camera watching that door) ---
@app.get("/api/floorplan/doors", response_model=DoorsListResponse)
async def list_floorplan_doors():
    """List all doors (points) on the floor plan."""
    doors = load_doors(_data_dir)
    return DoorsListResponse(doors=[DoorItem(**d) for d in doors])


@app.post("/api/floorplan/doors", response_model=DoorItem)
async def create_floorplan_door(body: CreateDoorBody):
    """Add a door point (x,y normalized 0-1, feed_id, name, allowed_roles, etc.)."""
    door = add_door(_data_dir, body.model_dump())
    return DoorItem(**door)


@app.patch("/api/floorplan/doors/{door_id}")
async def update_floorplan_door(door_id: str, body: UpdateDoorBody):
    """Update door name, point, feed_id, allowed_roles, restriction_level, or rules."""
    updates = body.model_dump(exclude_unset=True)
    updated = update_door(_data_dir, door_id, updates)
    if updated is None:
        raise HTTPException(404, "Door not found")
    return {"ok": True}


@app.delete("/api/floorplan/doors/{door_id}")
async def delete_floorplan_door(door_id: str):
    """Delete a door point."""
    if not delete_door(_data_dir, door_id):
        raise HTTPException(404, "Door not found")
    return {"ok": True}


# --- Door access (face + door feeds, movement, alerts) ---
_DEFAULT_DOOR_AREAS = [
    {"id": "office1", "name": "Office 1", "face_feed_id": 0, "door_feed_id": 1, "allowed_roles": ["Admin"]},
    {"id": "office2", "name": "Office 2", "face_feed_id": 2, "door_feed_id": 3, "allowed_roles": ["Admin", "Worker"]},
]


@app.get("/api/door/areas", response_model=DoorAreasResponse)
async def get_door_areas():
    """List door access areas (Office 1, Office 2: face_feed_id, door_feed_id, allowed_roles)."""
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
    """Update door areas config. Each area has name, face_feed_id, door_feed_id, allowed_roles."""
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
    """Run door detection on image. Permissions from floor plan door point (feed_id) if set, else door_areas."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    try:
        contents = await file.read()
    except Exception as e:
        raise HTTPException(400, f"Failed to read file: {e}") from e
    areas = load_door_areas(_data_dir)
    door_config = get_door_by_feed_id(_data_dir, int(feed_id))
    try:
        result = detect_doors(contents, int(feed_id), areas, door_config=door_config)
        return DoorDetectResponse(**result)
    except Exception:
        from app.door_service import _safe_fallback
        fallback = _safe_fallback(int(feed_id), door_config, areas)
        return DoorDetectResponse(**fallback)


@app.post("/api/feed/analyze", response_model=FeedAnalyzeResponse)
async def feed_analyze(
    file: UploadFile = File(...),
    feed_id: int = Form(0),
):
    """Run face recognition and door detection on the same frame. Use this for a single feed that watches a door (camera in office facing door). Returns both detections and door result; permissions from floor plan door point."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")
    try:
        contents = await file.read()
    except Exception as e:
        raise HTTPException(400, f"Failed to read file: {e}") from e
    svc = get_face_service()
    areas = load_door_areas(_data_dir)
    door_config = get_door_by_feed_id(_data_dir, int(feed_id))
    try:
        detections = svc.recognize(contents)
        detections_dict = [d if isinstance(d, dict) else d.model_dump() for d in detections]
        set_last_recognition(int(feed_id), detections_dict)
    except ValueError:
        detections_dict = []
    try:
        door_result = detect_doors(contents, int(feed_id), areas, door_config=door_config)
    except Exception:
        from app.door_service import _safe_fallback
        door_result = _safe_fallback(int(feed_id), door_config, areas)
    return FeedAnalyzeResponse(
        detections=detections_dict,
        doors=door_result.get("doors", []),
        movement_detected=door_result.get("movement_detected", False),
        area_name=door_result.get("area_name"),
        last_person=door_result.get("last_person"),
        allowed=door_result.get("allowed", True),
        alert=door_result.get("alert", False),
        hint=door_result.get("hint"),
    )


# Mount static frontend after build (optional; dev uses Vite dev server)
_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="static")
