# Hof Capital Inspection — Client Dashboard

Seamless authentication and inspection using facial recognition. This app provides:

- **4 camera feed slots** with a **dropdown per feed** to select the camera (Camo Studio, Iriun, built-in, etc.).
- **Live view** with **live analysis**: faces are detected and outlined with a **colored perimeter** — **green = authorized** (known face in DB), **red = unknown**.
- **Register face**: upload a photo + name to add someone to the known-face database so they show as authorized on the feeds.

## What you need

- **Python 3.10+** and **Node 18+** on your laptop.
- **Chrome** (for localhost and camera access).
- **Camo Studio** (and/or Iriun): pair your phones so they appear as virtual webcams. The app will list them in the dropdowns once you allow camera permission.

## Run locally

### 1. Backend (FastAPI)

```bash
cd backend
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # Mac/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Leave this running. The first request that triggers face recognition may take a few seconds (model load). The first time you register or recognize a face, the ArcFace ONNX model (~250MB) is downloaded once to `backend/data/models/`; no C++ Build Tools or InsightFace build is required.

### 2. Frontend (Vite)

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in Chrome. Allow camera access when prompted.

### 3. Using the dashboard

1. **Register faces:** Use the form at the top: enter a name, choose a clear face photo, click “Register face.” Those people will appear as **authorized (green)** when seen on any feed.
2. **Feeds:** For each of the 4 slots, open the dropdown and select a camera (e.g. your two Camo cameras). Unused slots can stay on “No camera.”
3. **Perimeters:** Green box = recognized and authorized; red box = unknown (not in DB or not allowed).

When you add more phones (e.g. 2 more via Camo), they will show up in the same dropdowns; no code changes needed.

## Project layout

- `backend/` — FastAPI app: `/api/register`, `/api/recognize`, known-face storage under `backend/data/`.
- `frontend/` — React + Vite: 4 feeds, camera dropdown, live view, overlay drawing.
- `door-detection/` — **Cloned repo**: [YOLOv8 Door detection (visually impaired)](https://github.com/sayedmohamedscu/YOLOv8-Door-detection-for-visually-impaired-people). Use for door detection on the camera that faces the door; train once to get `doors.pt` (see `docs/DOOR_MOVEMENT_AND_ACCESS.md`).
- `docs/DOOR_MOVEMENT_AND_ACCESS.md` — **Door movement + access**: one camera on the person (face + role), one on the door; when the door moves, apply role vs door restrictions and alert. Includes which repo to use and how to detect door movement.
- `docs/ZONE_CAMERA_MAPPING.md` — How to map floor-plan zones to the camera view (homography approach; optional).
- `RECOMMENDATIONS.md` — Repo recommendations and what you need to provide for further development.

## License

Use as needed for your hackathon / project.
