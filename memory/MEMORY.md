# Facey Project Memory

## Project Overview
Hof Capital Inspection dashboard: face recognition + door access control + zone security.
- Backend: FastAPI at port 8000, Python venv at `backend/venv/`
- Frontend: React+Vite at port 5173 (proxies /api → 8000)
- Run backend: `cd backend && source venv/bin/activate && uvicorn app.main:app --reload`
- Run frontend: `cd frontend && npm run dev`

## Key Architecture
- `backend/app/main.py` – All FastAPI endpoints (35 total after security features)
- `backend/app/face_service.py` – ArcFace ONNX face recognition
- `backend/app/door_service.py` – YOLOv8 door detection + movement tracking
- `backend/app/zone_service.py` – YOLOv8n person detection + zone crossing logic (NEW)
- `backend/app/security_service.py` – Alert log persistence (NEW)
- `backend/app/camera_zones_store.py` – Camera zone persistence (NEW)
- `backend/data/security_alerts.json` – Persisted alert log (auto-created)
- `backend/data/camera_zones.json` – Camera zone definitions (auto-created)
- `frontend/src/CameraFeed.jsx` – Live feed + zone drawing UI
- `frontend/src/components/SecurityAlerts.jsx` – Alert log panel (NEW)

## Security Features Implemented
### Feature 1: Unauthorized Door Access Alert
- When door moves AND last face is unauthorized → alert fires
- Logged to `security_alerts.json` with 15s per-feed cooldown
- Alert type: `"unauthorized_door_access"`
- Real-time red banner on camera feed overlay

### Feature 2: Restricted Zone Enforcement
- Operators draw zones directly on live camera feeds (click points on canvas)
- Zone types: **polygon** (person inside triggers alert) or **line** (crossing triggers alert)
- YOLOv8n detects persons, uses feet position (bbox bottom-center) normalized 0-1
- Line crossing tracked per-person per-zone via side-of-line state machine
- Logged as `"zone_presence"` or `"line_crossing"` alert types
- 15s cooldown per (feed_id, zone_id) pair to prevent alert flooding

## New API Endpoints
- `GET /api/security/alerts` – Get recent alerts (newest first)
- `DELETE /api/security/alerts` – Clear all alerts
- `POST /api/security/alerts/{id}/acknowledge` – Acknowledge one alert
- `GET /api/camera-zones` – List zones (optionally ?feed_id=N)
- `POST /api/camera-zones` – Create zone
- `PATCH /api/camera-zones/{id}` – Update zone
- `DELETE /api/camera-zones/{id}` – Delete zone

## Zone Response Shape (zone_alerts field added to all analyze endpoints)
```json
{
  "zone_id": "...", "zone_name": "...", "zone_type": "polygon|line",
  "alert_type": "zone_presence|line_crossing",
  "person_bbox": [x1,y1,x2,y2],   // pixel coords
  "person_feet_n": [nx, ny],        // normalized 0-1
  "person_name": "...", "person_role": "...", "authorized": false
}
```

## Data File Locations
- `backend/data/faces_meta.json` – Registered faces
- `backend/data/embeddings.npy` – ArcFace embeddings
- `backend/data/camera_zones.json` – Camera-view zones (NEW)
- `backend/data/security_alerts.json` – Alert log (NEW)
- `backend/data/models/doors.pt` – Door detection model
- `backend/data/models/yolov8n.pt` – Person detection model (auto-downloaded)

## CSS Classes (new)
- `.security-alerts-section` – Alert panel container
- `.alert-badge` – Red count badge on toggle button
- `.zone-draw-panel` – Zone drawing form below video
- `.feed-zones-list` – Zone chips list in feed
- `.zone-alert-badge` – Orange alert count in feed footer
