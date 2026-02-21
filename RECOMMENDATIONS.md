# Repo recommendations & what we need from you

## Best repos to fork or lean on

### 1. **Primary reference: [AarambhDevHub/multi-cam-face-tracker](https://github.com/AarambhDevHub/multi-cam-face-tracker)** (fork or copy patterns)
- **Why:** Multi-camera support, InsightFace, known-faces DB, SQLite, config-driven cameras, live dashboard, alerts. Fits “4 feeds + recognition + known vs unknown” best.
- **Caveat:** Desktop PyQt5 app, not browser. Use its **core/** (detection, recognition, known_faces) and **config** patterns; we build a **web backend (FastAPI) + browser dashboard** that uses the same ideas (camera slots, face DB, match vs DB).

### 2. **Backend / API reference: [SthPhoenix/InsightFace-REST](https://github.com/SthPhoenix/InsightFace-REST)**
- **Why:** Production-ready FastAPI + InsightFace (detection + embeddings), Docker, many models. Use as the **recognition engine** (run as a service) or copy its API shape (e.g. `/extract` → we add our own “match to DB” and “authorized” logic).
- **Use case:** Either run InsightFace-REST as a microservice and our app calls it for embeddings, or we embed InsightFace in our FastAPI app (simpler for a single backend on your laptop).

### 3. **Optional: [CJBuzz/Real-time-FRS-2.0](https://github.com/CJBuzz/Real-time-FRS-2.0)** (simpliFRy + gotendance)
- **Why:** Flask + InsightFace + Voyager (vector search), multi-camera (RTSP). Good if we later want RTSP or a separate attendance UI; for **browser Camo feeds** we’re not using RTSP, so we only reuse the “embed + match” idea.

---

## What you need to do on your side

So we can do everything on our side and you just run it:

1. **Environment**
   - **Python:** 3.10 or 3.11 installed (for backend + InsightFace).
   - **Node:** 18+ (for frontend build/dev).
   - **Chrome:** For localhost (as you wanted).

2. **Camo Studio**
   - Pair your 2 iPhones so they show as 2 virtual cameras on the laptop.
   - When you open the app in Chrome and grant camera permission, those 2 (and any others) will appear in the **camera dropdown** for each of the 4 feed slots. No extra config from you beyond selecting the right device per slot.

3. **Iriun**
   - If you use Iriun as additional webcam(s), same idea: they’ll show up in the same dropdowns once Chrome has permission.

4. **What you don’t need to give us**
   - No recording or “pre-scan” of the room. We only use **uploaded face photos** (e.g. from a form) and optional **roles**; “unknown” = not in DB or not allowed.
   - No hardware (doors, etc.). We only do software: 4 feeds, dropdown, live view, and colored perimeter by auth status.

5. **For the demo**
   - Run backend + frontend (instructions in README).
   - Open `http://localhost:<port>` in Chrome, allow camera access.
   - For each of the 4 feeds, pick a camera from the dropdown (Camo 1, Camo 2, or “none” for empty slots). When you have more phones, select them in the same way.

---

## What we’re building in this repo (no fork required)

We’re implementing in **this repo** so you have one place to run and extend:

- **Backend (FastAPI):** Runs on your laptop; `/api/register` (upload face + name/role), `/api/recognize` (image → list of faces with bbox + identity + authorized). Known faces stored in a local DB/file.
- **Frontend (React + Vite):** Client dashboard at localhost with:
  - **4 camera feed slots**, each with a **dropdown to select camera** (Camo, Iriun, built-in, etc.).
  - **Live view** (no labels for now).
  - **Live analysis:** frames sent to backend; we draw a **visual perimeter** (e.g. colored box) around each person: **green = authorized**, **red = unknown/unrecognized** (and we can add yellow later for “known but wrong role,” etc.).

Once this works with 2 phones and 4 slots, adding more phones is just selecting them in the same dropdowns; no code change needed.
