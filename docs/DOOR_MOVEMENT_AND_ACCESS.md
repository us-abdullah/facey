# Door movement + facial recognition access control

This doc describes the **door-movement** approach: one camera on the person (face + role), one camera on the door; when the door moves we treat that as “person entering/exiting” and apply role vs. door restrictions.

## Setup

- **Camera 1 (at entrance, facing person)**  
  - Used for **facial recognition** (existing pipeline).  
  - Output: identity + **role** (and thus effective restriction level for the area).

- **Camera 2 (farther back, facing the door)**  
  - Used only for **door detection** and **door movement** (open/close).  
  - No need to recognize who; we correlate by time with Camera 1.

- **Logic**  
  - When **door movement** is detected (e.g. open→closed or closed→open), we treat it as “someone just went through this door.”  
  - We take the **last recognized person** from Camera 1 (same time window, e.g. last 5–10 seconds) and apply **that person’s role** against the **restriction for that door/room**.  
  - **Response**: allow or alert (e.g. “Visitor entered restricted Office 1”).

- **Room/door identity**  
  - On the **floor plan**: user places a point and labels the door (e.g. “Office 1”, “Office 2”) and sets that door’s restrictions (allowed roles, etc.).  
  - In real life: **one Camera 2 per door** (or one feed that sees one door). So “which door” = which camera/feed ID. We **link** that camera/feed to the floor-plan door label (e.g. “Feed 3 = Office 1 door”).  
  - Optionally later: use a model that can distinguish “Office 1 door” vs “Office 2 door” in one frame (custom-trained YOLO with those classes); for MVP, one camera per door is enough.

---

## Repo to use for door detection (YOLOv8)

**Recommended: clone and use this repo**

- **Repository**: [sayedmohamedscu/YOLOv8-Door-detection-for-visually-impaired-people](https://github.com/sayedmohamedscu/YOLOv8-Door-detection-for-visually-impaired-people)  
- **Why**: YOLOv8 (Ultralytics), includes a trained **doors.pt** weight file, Python API, and works on standard hardware.  
- **What it gives you**: Detects “door” in an image (bounding box). Does **not** by default classify open vs closed; “door movement” can be implemented by **state over time** (see below).

### Clone and install (already done in this project)

The repo is already cloned at **`door-detection/`** in this project.

```bash
# If you need to clone again elsewhere:
git clone https://github.com/sayedmohamedscu/YOLOv8-Door-detection-for-visually-impaired-people.git door-detection
cd door-detection
pip install ultralytics
```

**Getting a door model (weights):**

- The repo does **not** ship a pre-built `doors.pt` in the clone (large file / LFS). You have two options:
  1. **Train once** using the repo’s notebook and the [Kaggle doors dataset](https://www.kaggle.com/datasets/sayedmohamed1/doors-detection). The notebook saves `runs/detect/train2/weights/best.pt`. Copy that to `door-detection/doors.pt` (or your backend) for inference.
  2. **Use a generic YOLOv8 model** for a quick test: `YOLO("yolov8n.pt")` detects many COCO classes; for production you want a door-trained `best.pt` or `doors.pt` from option 1 (or from [MiguelARD/DoorDetect-Dataset](https://github.com/MiguelARD/DoorDetect-Dataset) converted to YOLOv8 and trained).

### Minimal inference (door detection only)

```python
from ultralytics import YOLO

# Use your trained door weights, or yolov8n.pt for testing
model = YOLO("doors.pt")  # or path to best.pt from training
results = model.predict("frame.jpg", conf=0.3)
for r in results:
    for box in r.boxes:
        # box.xyxy = [x1, y1, x2, y2], box.cls = class index
        print("door", box.xyxy.tolist())
```

Use this on each frame from the door-facing camera. You can run it from this project’s backend by adding `ultralytics` to `backend/requirements.txt` and pointing the model path to `door-detection/doors.pt` (or a copied `best.pt`).

---

## Detecting “door movement”

- **Option A – Bbox change over time**  
  - Every few hundred ms, run door detection on the door-camera frame.  
  - Track the door bbox (e.g. center + size). If the bbox **appears**, **disappears**, or **changes size/position** beyond a threshold, consider that “door movement” (someone opened/closed it).  
  - Simple, no extra model; may have false positives (lighting, angle).

- **Option B – Open vs closed (recommended)**  
  - Use a model that classifies **open_door** vs **closed_door**.  
  - **“Is My Door Open?”** on Roboflow: [universe.roboflow.com/alanlenhart/is-my-door-open](https://universe.roboflow.com/alanlenhart/is-my-door-open) — 2 classes: `closed_door`, `open_door`.  
  - Export the dataset to YOLOv8 format, then train a small YOLOv8 model (or use Roboflow Hosted API) to get a **state** per frame.  
  - **Door movement** = state change (e.g. closed→open or open→closed) in a short time window.

For MVP, Option A is enough: “door bbox changed or appeared” → trigger the “person went through door” logic. Later, add Option B for cleaner “opened” vs “closed” events.

---

## Linking door to floor plan and restrictions

1. **Floor plan**  
   - User draws/labels as today; adds **door points** with a **door name** (e.g. “Office 1”, “Server Room”) and the **restriction** for that door (allowed roles, time rules, etc.).

2. **Camera assignment**  
   - In the app, user assigns “Camera 2 / Feed 2” = “Office 1 door”. So when we get a “door movement” event from that feed, we know the **door_id** / door name and thus the restriction to check.

3. **When door movement is detected**  
   - Get last recognized person from the **face camera** (same time window).  
   - Get that person’s **role**.  
   - Get **door’s** allowed roles / restriction level.  
   - If role is **not** allowed for that door → **alert** (and optionally log).

No need for the model to output “Office 1 door” vs “Office 2 door” if we use one door camera per door and link camera↔door in config.

---

## Summary

| Piece              | Solution |
|--------------------|----------|
| Door detection     | Clone **sayedmohamedscu/YOLOv8-Door-detection-for-visually-impaired-people**, use **doors.pt** + Ultralytics. |
| Door movement      | MVP: door bbox change over time. Better: train or use “Is My Door Open?” (open/closed) and use state change. |
| Which room/door    | One camera per door; link camera/feed ID to floor-plan door label and its restrictions. |
| Role vs restriction| Existing: person’s role from face cam; door’s allowed roles from floor plan; compare and alert. |

You do **not** need a separate “3D” or homography pipeline; you only need door detection + optional open/closed state and the existing face + floor-plan data.
