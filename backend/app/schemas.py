from pydantic import BaseModel


class DetectionItem(BaseModel):
    bbox: list[float]  # [x1, y1, x2, y2] in image coordinates
    identity_id: str | None  # from DB if matched
    name: str | None
    role: str | None  # e.g. Visitor, Worker, Admin
    authorized: bool  # True if known and allowed
    score: float  # match confidence 0..1


class RecognizeResponse(BaseModel):
    detections: list[DetectionItem]


class RegisterResponse(BaseModel):
    identity_id: str
    name: str
    message: str


class FaceListItem(BaseModel):
    identity_id: str
    name: str
    role: str
    authorized: bool


class FacesListResponse(BaseModel):
    faces: list[FaceListItem]


class UpdateFaceBody(BaseModel):
    name: str | None = None
    role: str | None = None
    authorized: bool | None = None


class RolesListResponse(BaseModel):
    roles: list[str]


class CreateRoleBody(BaseModel):
    name: str


# Floor plan zones: points are normalized 0-1 (relative to image size)
class ZoneRules(BaseModel):
    time_start: str | None = None  # "09:00"
    time_end: str | None = None    # "17:00"
    days: list[int] | None = None  # 0=Mon .. 6=Sun; empty or null = all days


# Doors = points on floor plan; each door has one feed_id (camera watching that door)
class DoorItem(BaseModel):
    id: str
    name: str
    point: list[float]  # [x, y] normalized 0-1
    feed_id: int  # camera feed index for this door (same feed does face + door analysis)
    allowed_roles: list[str] = []
    restriction_level: str = "restricted"
    rules: ZoneRules | None = None


class DoorsListResponse(BaseModel):
    doors: list[DoorItem]


class CreateDoorBody(BaseModel):
    name: str
    point: list[float]
    feed_id: int
    allowed_roles: list[str] = []
    restriction_level: str = "restricted"
    rules: ZoneRules | None = None


class UpdateDoorBody(BaseModel):
    name: str | None = None
    point: list[float] | None = None
    feed_id: int | None = None
    allowed_roles: list[str] | None = None
    restriction_level: str | None = None
    rules: ZoneRules | None = None


class ZoneItem(BaseModel):
    id: str
    name: str
    type: str  # "rect" | "polygon" | "path"
    points: list[list[float]]  # [[x,y],...] normalized 0-1
    allowed_roles: list[str] = []
    restriction_level: str = "restricted"  # "restricted" | "authorized_only" | "public"
    rules: ZoneRules | None = None


class ZonesListResponse(BaseModel):
    zones: list[ZoneItem]


class CreateZoneBody(BaseModel):
    name: str
    type: str
    points: list[list[float]]
    allowed_roles: list[str] = []
    restriction_level: str = "restricted"
    rules: ZoneRules | None = None


class UpdateZoneBody(BaseModel):
    name: str | None = None
    allowed_roles: list[str] | None = None
    restriction_level: str | None = None
    rules: ZoneRules | None = None


# --- Door access (face feed + door feed per area) ---
class DoorAreaItem(BaseModel):
    id: str
    name: str
    face_feed_id: int
    door_feed_id: int
    allowed_roles: list[str] = []


class DoorAreasResponse(BaseModel):
    areas: list[DoorAreaItem]


class DoorAreaUpdateBody(BaseModel):
    areas: list[DoorAreaItem]


class DoorDetectResponse(BaseModel):
    doors: list[dict]  # [{ "bbox": [x1,y1,x2,y2] }, ...]
    movement_detected: bool
    area_name: str | None
    last_person: dict | None  # { "name", "role", "identity_id" } or null
    allowed: bool  # True if last_person's role is in area's allowed_roles
    alert: bool  # True if movement and not allowed (reaction hook later)
    hint: str | None = None  # Shown when no doors detected or detector unavailable


# Combined face + door analysis on same frame (one feed = camera at door)
class FeedAnalyzeResponse(BaseModel):
    detections: list[DetectionItem]  # faces
    doors: list[dict]
    movement_detected: bool
    area_name: str | None
    last_person: dict | None
    allowed: bool
    alert: bool
    hint: str | None = None
