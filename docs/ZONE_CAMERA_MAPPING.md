# Mapping floor-plan zones to the camera view (and alerts)

This doc describes how to go from the **2D floor plan with restricted zones** to the **live camera view**: show zones in the “real” camera image and trigger **alerts when a recognized person is in a restricted area**.

## The problem

- **Floor plan**: You have a 2D image and zones (polygons in normalized 0–1 coordinates) with restriction level, allowed roles, and optional time/days.
- **Camera**: You have a live feed; faces are detected and recognized (identity + role).
- **Goal**:  
  - Know when a **recognized person is physically inside** a restricted zone.  
  - Optionally **draw zone boundaries** on the camera image.  
  - **Alert** when someone is in a zone they’re not allowed in (by role/restriction/time).

So we need a mapping: **camera pixel position of the person → floor-plan position → “is this point inside this zone?”**.

## Approach: 2D homography (no separate 3D world)

You don’t need a full 3D engine or another “3D app.” The camera image is a **2D projection** of the scene. If the camera is **fixed** and looks at the floor/room, we can relate:

- **Camera image coordinates** (pixels)  
- **Floor-plan coordinates** (normalized 0–1, same as your zone `points`)

using a **planar homography** (a 3×3 matrix **H**). So:

- **Person in image** → one 2D point (e.g. estimated “foot” or bottom of bbox) → multiply by **H** → point on floor plan → **point-in-polygon** for each zone → apply zone rules (role, restriction, time) → **alert** if not allowed.
- **Zone on floor plan** → polygon in 0–1 → multiply each vertex by **H⁻¹** → polygon in camera pixels → **draw on the overlay** so zones appear “boxed out” in the camera view.

So the “3D” you care about is really: **camera 2D ↔ floor-plan 2D**, with a one-time **calibration** per camera.

### What you need per camera

1. **Calibration**: Define how camera image lines up with the floor plan.  
   - **Option A (recommended for MVP)**: User clicks **4+ corresponding point pairs** (same physical point on floor plan and in a camera frame). Backend computes **H** (e.g. with `cv2.getPerspectiveTransform` or `cv2.findHomography`) and stores it per camera (e.g. by `deviceId` or a named “camera slot”).
   - **Option B**: If the floor plan is a direct top-down view and the camera is top-down too, a simple scale+translate might be enough; homography still generalizes to perspective.

2. **Person position in the image**:  
   - Face bbox gives **head** position. For “person in zone” we ideally want a point on the **floor** (e.g. feet).  
   - **MVP**: Use **bottom-center of the face bbox** (or center) as a proxy; document that calibration assumes typical head height / camera angle.  
   - **Later**: Add a body detector and use **bottom-center of body bbox** for better floor position.

3. **Pipeline**:  
   - **Recognize** (existing): image → face detections (bbox, identity, role).  
   - **Map**: For each detection, convert bbox bottom-center (or center) from image coords → floor-plan coords using **H**.  
   - **Zone check**: For each zone, **point-in-polygon** (e.g. ray-casting or `cv2.pointPolygonTest`).  
   - **Rules**: Restriction level + allowed roles + time/days (from zone) vs. person’s role and current time → **allowed or not**.  
   - **Alert**: If not allowed, record an event and/or show on UI / send webhook.

4. **Overlay**:  
   - Load zones (normalized polygon). Transform each polygon to camera space with **H⁻¹**, draw on the same overlay canvas where you draw face boxes. That’s the “restricted/whatever area boxed out in the real [camera] world.”

## Do you need another repo?

**Short answer: no for the core feature.** You can implement calibration, zone-check, and overlays **in this repo**.

- **Backend (this repo)**  
  - Already has: OpenCV (for face detection), floor plan + zones API, face recognition.  
  - Add:  
    - **Calibration store** (e.g. `data/camera_calibration.json`: `deviceId` or `slotId` → homography matrix or 4+ point pairs).  
    - **Endpoint** to save/load calibration (e.g. POST/GET per camera/slot).  
    - **Endpoint** that does “recognize + zone check”: same input as `/api/recognize`, plus `camera_id`/`slot`; returns detections **and** per-detection `zone_id` (if any) and `allowed_in_zone: bool`, and optionally list of **alerts** (person X in restricted zone Y).  
  - Homography and point-in-polygon are simple in Python (OpenCV + NumPy).

- **Frontend (this repo)**  
  - **Calibration UI**: e.g. on the dashboard or a “Calibrate camera” page: show floor plan and one camera frame side-by-side; user clicks 4+ matching points; send to backend to compute and save **H**.  
  - **Live view**: Keep using existing `CameraFeed`; either:  
    - Call the new “recognize + zone check” endpoint and draw zone polygons on the overlay (using **H⁻¹** and zone polygons from API), and draw alerts (e.g. red border + “Restricted” when `allowed_in_zone === false`).

So: **one repo** can contain floor plan, zones, face recognition, calibration, zone–camera mapping, and alerts.

**When a second repo *might* make sense**

- You want a **separate deployable service** that runs on another machine (e.g. on-site gateway): it reads camera streams, calls this app’s API for config (floor plan, zones, calibration) and for recognition (or a combined recognize+zone endpoint), and only sends back alerts / overlays. That can still be a **thin client** that uses this API; the “heavy” logic (homography, zone rules) can stay in this backend. So the second repo would be “camera ingestion + API client,” not a full duplicate of the mapping logic.  
- Or you want a completely different stack (e.g. C++/GPU service) for low-latency video; then the other repo would implement the same math (homography + point-in-polygon) and maybe call this app only for identities and zone config.

**Recommendation**: Implement **calibration + zone check + overlays + alerts in this repo** first. Add a second repo only if you need a separate deployment (e.g. edge device) or a different runtime.

## Implementation checklist (in this repo)

1. **Backend**  
   - [ ] **Calibration store**: e.g. `camera_calibration.json` — key by camera/slot, value = homography 3×3 (or 4+ point pairs).  
   - [ ] **Endpoints**: GET/POST calibration for a camera/slot; optional GET that returns floor plan + zones + calibration for a slot (for overlay).  
   - [ ] **Homography helpers**: `image_point → floor_plan_point`, `floor_plan_polygon → image_polygon` (using H and H⁻¹).  
   - [ ] **Point-in-polygon**: for a point in 0–1 floor plan, return which zone(s) contain it (and zone details).  
   - [ ] **Recognize + zone check endpoint**: input = image + camera_id/slot; run existing recognize; for each detection, map to floor plan, run zone check, apply zone rules (role, time, days); return detections + `in_zone`, `allowed_in_zone`, `alerts`.  
   - [ ] **Optional**: Persist alerts (e.g. `alerts.json` or DB) and an endpoint to list recent alerts.

2. **Frontend**  
   - [ ] **Calibration flow**: Page or modal: select camera → show snapshot + floor plan; click 4+ corresponding points; submit → backend computes and saves H.  
   - [ ] **Camera feed overlay**: Fetch zones + calibration for the selected camera; project zone polygons to image space with H⁻¹; draw them on the same overlay (e.g. semi-transparent fill + stroke).  
   - [ ] **Alert display**: When response includes `allowed_in_zone: false` or `alerts`, show on the feed (e.g. red zone border, “Restricted” badge, or a small alerts list).  
   - [ ] **Optional**: “Alerts” panel or history from backend.

3. **Data**  
   - Zones already have: `points` (0–1), `restriction_level`, `allowed_roles`, `rules` (time/days).  
   - Calibration: one homography (or point pairs) per camera/slot; image size at calibration time (to normalize if needed).

4. **Person position**  
   - MVP: Use **bottom-center of face bbox** in image coords, then `H @ [x, y, 1]` → normalize to 0–1 for floor plan.  
   - Later: body bbox bottom-center if you add a body detector.

This gives you: **zones drawn on the camera view** and **alerts when a recognized person is in a restricted area**, all inside the current repo, without a separate “3D” application.
