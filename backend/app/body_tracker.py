"""
Per-feed body tracker.

When a face is recognised the identity is "locked" to the person's body bbox.
Subsequent frames: if the face leaves frame but the body is still visible
(matched by IoU) we keep returning the last known identity so the UI always
shows who the person is even when they turn away or move out of face range.

Identity requires TWO consecutive high-confidence face matches before being
locked to a body track (debounce), preventing a single noisy frame from
permanently branding the wrong person.
"""
from __future__ import annotations

import time
import uuid

IDENTITY_TTL       = 6.0    # seconds a locked identity stays alive without a new face match
BODY_TTL           = 3.0    # seconds before a body track is removed when not seen
IOU_THRESH         = 0.45   # min IoU to re-associate a bbox to an existing track
FACE_OVERLAP       = 0.40   # min fraction of face area that must overlap the body bbox
MIN_LOCK_SCORE     = 0.62   # face match must score at least this to be eligible for locking
CONFIRM_FRAMES     = 2      # must see the same identity at MIN_LOCK_SCORE for N frames in a row

# feed_id → list of track dicts
_tracks: dict[int, list[dict]] = {}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    denom = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / denom if denom > 0 else 0.0


def _face_to_person(face_bbox: list[float], person_bboxes: list[list[float]]) -> int | None:
    """Return index of person bbox that best contains/overlaps the face bbox."""
    best_ov, best_i = FACE_OVERLAP, None
    fx1, fy1, fx2, fy2 = face_bbox
    fa = max((fx2 - fx1) * (fy2 - fy1), 1e-6)
    for i, (px1, py1, px2, py2) in enumerate(person_bboxes):
        iw = min(fx2, px2) - max(fx1, px1)
        ih = min(fy2, py2) - max(fy1, py1)
        if iw > 0 and ih > 0:
            ov = (iw * ih) / fa
            if ov > best_ov:
                best_ov, best_i = ov, i
    return best_i


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def update(
    feed_id: int,
    person_bboxes: list[list[float]],
    face_detections: list[dict],
) -> list[dict]:
    """
    Update per-feed body tracks and return augmented detections.

    Identity is only locked to a body track after CONFIRM_FRAMES consecutive
    high-confidence face matches for the same identity_id on that track.
    Once locked, it persists for IDENTITY_TTL seconds without needing a face.

    Returns one detection per detected person body + any unmatched face detections.
    Schema matches DetectionItem (bbox, identity_id, name, role, authorized, score).
    """
    now = time.time()
    feed_tracks = _tracks.setdefault(feed_id, [])

    # Drop stale tracks
    feed_tracks[:] = [t for t in feed_tracks if now - t["last_seen"] < BODY_TTL]

    # -----------------------------------------------------------------------
    # Re-associate each person bbox to an existing track (greedy, best-IoU)
    # -----------------------------------------------------------------------
    used_ids: set[str] = set()
    person_to_track: list[dict | None] = [None] * len(person_bboxes)

    for p_idx, pbbox in enumerate(person_bboxes):
        best_iou, best_t = 0.0, None
        for t in feed_tracks:
            if t["_id"] in used_ids:
                continue
            v = _iou(pbbox, t["bbox"])
            if v > best_iou:
                best_iou, best_t = v, t

        if best_iou >= IOU_THRESH and best_t is not None:
            best_t["bbox"]      = pbbox
            best_t["last_seen"] = now
            used_ids.add(best_t["_id"])
            person_to_track[p_idx] = best_t
        else:
            new_t: dict = {
                "_id":             str(uuid.uuid4()),
                "bbox":            pbbox,
                # Confirmed identity (locked)
                "identity_id":     None,
                "name":            None,
                "role":            None,
                "authorized":      False,
                "score":           0.0,
                "last_face_time":  0.0,
                # Pending confirmation
                "pending_id":      None,
                "pending_frames":  0,
                "last_seen":       now,
            }
            feed_tracks.append(new_t)
            used_ids.add(new_t["_id"])
            person_to_track[p_idx] = new_t

    # -----------------------------------------------------------------------
    # Update tracks from face detections (with debounce)
    # -----------------------------------------------------------------------
    for face in face_detections:
        if not face.get("identity_id"):
            continue
        score = face.get("score", 0.0)
        if score < MIN_LOCK_SCORE:
            continue

        p_i = _face_to_person(face["bbox"], person_bboxes)
        if p_i is None:
            continue
        t = person_to_track[p_i]
        if t is None:
            continue

        fid = face["identity_id"]

        if t.get("pending_id") == fid:
            # Same identity seen again – increment confirmation counter
            t["pending_frames"] += 1
        else:
            # New or different candidate – reset counter
            t["pending_id"]     = fid
            t["pending_frames"] = 1

        # Only lock once we've seen CONFIRM_FRAMES consecutive matches
        if t["pending_frames"] >= CONFIRM_FRAMES:
            t["identity_id"]   = fid
            t["name"]          = face.get("name")
            t["role"]          = face.get("role")
            t["authorized"]    = face.get("authorized", False)
            t["score"]         = score
            t["last_face_time"] = now

    # -----------------------------------------------------------------------
    # Build output
    # -----------------------------------------------------------------------
    out: list[dict] = []
    for p_idx, pbbox in enumerate(person_bboxes):
        t = person_to_track[p_idx]
        identity_id = name = role = None
        authorized  = False
        score       = 0.0

        if t and t.get("identity_id"):
            age = now - t["last_face_time"]
            if age <= IDENTITY_TTL:
                identity_id = t["identity_id"]
                name        = t["name"]
                role        = t["role"]
                authorized  = t["authorized"]
                score       = t["score"]

        out.append({
            "bbox":        pbbox,
            "identity_id": identity_id,
            "name":        name,
            "role":        role,
            "authorized":  authorized,
            "score":       score,
        })

    # Include face detections that had no matching body bbox
    for face in face_detections:
        if _face_to_person(face["bbox"], person_bboxes) is None:
            out.append(face)

    return out
