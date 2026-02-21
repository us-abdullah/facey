"""
Face registration and recognition using OpenCV (detection) + ONNX ArcFace (embedding).
No InsightFace package — works on Windows without C++ Build Tools.
Stores embeddings and metadata in data_dir.
"""
from __future__ import annotations

import io
import json
import uuid
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps

# ArcFace ONNX model URL (no login required)
ARCFACE_ONNX_URL = "https://huggingface.co/garavv/arcface-onnx/resolve/main/arc.onnx"
# OpenCV DNN face detector (more accurate than Haar)
DNN_DEPLOY_URL = "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/dnn/face_detector/deploy.prototxt"
DNN_WEIGHTS_URL = "https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel"

_face_detector_haar = None
_face_detector_dnn = None  # (net, conf_threshold)
_arcface_session = None
_arcface_input_name = None
_arcface_output_name = None

# Recognition: video frames often score lower than registration photo (lighting/angle). Keep threshold
# low enough so registered people match; 0.45 is a good balance for live video.
RECOGNITION_THRESHOLD = 0.50
# Margin between best and second-best match. Wider margin avoids misidentifying look-alikes.
RECOGNITION_MARGIN = 0.07
DEFAULT_ROLES = ["Visitor", "Analyst", "C-Level"]


def _get_detector_haar():
    global _face_detector_haar
    if _face_detector_haar is None:
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _face_detector_haar = cv2.CascadeClassifier(path)
    return _face_detector_haar


def _ensure_dnn_models(models_dir: Path) -> tuple[Path, Path]:
    models_dir.mkdir(parents=True, exist_ok=True)
    deploy_path = models_dir / "deploy.prototxt"
    weights_path = models_dir / "res10_300x300_ssd_iter_140000.caffemodel"
    if not deploy_path.exists():
        import urllib.request
        urllib.request.urlretrieve(DNN_DEPLOY_URL, deploy_path)
    if not weights_path.exists():
        import urllib.request
        urllib.request.urlretrieve(DNN_WEIGHTS_URL, weights_path)
    return deploy_path, weights_path


def _get_detector_dnn(models_dir: Path):
    global _face_detector_dnn
    if _face_detector_dnn is None:
        try:
            deploy_path, weights_path = _ensure_dnn_models(models_dir)
            net = cv2.dnn.readNetFromCaffe(str(deploy_path), str(weights_path))
            _face_detector_dnn = (net, 0.35)  # lower = accept more faces (0.35 for registration)
        except Exception:
            _face_detector_dnn = False  # fallback to Haar
    return _face_detector_dnn


def _ensure_arcface_model(models_dir: Path) -> Path:
    models_dir.mkdir(parents=True, exist_ok=True)
    model_path = models_dir / "arcface.onnx"
    if not model_path.exists():
        import urllib.request
        try:
            urllib.request.urlretrieve(ARCFACE_ONNX_URL, model_path)
        except Exception as e:
            raise ValueError(
                f"Could not download ArcFace model. Download manually from {ARCFACE_ONNX_URL} "
                f"and save as {model_path}. Error: {e}"
            )
    return model_path


def _get_arcface(models_dir: Path):
    global _arcface_session, _arcface_input_name, _arcface_output_name
    if _arcface_session is None:
        model_path = _ensure_arcface_model(models_dir)
        _arcface_session = ort.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
        _arcface_input_name = _arcface_session.get_inputs()[0].name
        _arcface_output_name = _arcface_session.get_outputs()[0].name
    return _arcface_session, _arcface_input_name, _arcface_output_name


def _preprocess_face_crop(bgr_crop: np.ndarray) -> np.ndarray:
    """Resize to 112x112 and normalize for ArcFace. Returns (1, 112, 112, 3)."""
    resized = cv2.resize(bgr_crop, (112, 112))
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    normalized = (rgb.astype(np.float32) - 127.5) / 128.0
    return normalized[np.newaxis, ...]


def _bbox_from_rect(x: int, y: int, w: int, h: int) -> list[float]:
    return [float(x), float(y), float(x + w), float(y + h)]


class FaceService:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.models_dir = self.data_dir / "models"
        self.meta_path = self.data_dir / "faces_meta.json"
        self.embeddings_path = self.data_dir / "embeddings.npy"
        self.ids_path = self.data_dir / "ids.json"
        self.roles_path = self.data_dir / "roles.json"
        self._meta: dict = {}
        self._embeddings: np.ndarray | None = None
        self._ids: list[str] = []
        self._roles: list[str] = []
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self._load()
        except Exception:
            self._meta = {}
            self._ids = []
            self._embeddings = np.zeros((0, 512), dtype=np.float32)
            self._roles = DEFAULT_ROLES.copy()

    def _load(self):
        try:
            if self.meta_path.exists():
                self._meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
                if not isinstance(self._meta, dict):
                    self._meta = {}
            else:
                self._meta = {}
        except Exception:
            self._meta = {}
        try:
            if self.ids_path.exists():
                self._ids = json.loads(self.ids_path.read_text(encoding="utf-8"))
                if not isinstance(self._ids, list):
                    self._ids = []
            else:
                self._ids = []
        except Exception:
            self._ids = []
        try:
            if self.embeddings_path.exists():
                self._embeddings = np.load(self.embeddings_path)
                if self._embeddings is None or not isinstance(self._embeddings, np.ndarray):
                    self._embeddings = np.zeros((0, 512), dtype=np.float32)
            else:
                self._embeddings = np.zeros((0, 512), dtype=np.float32)
        except Exception:
            self._embeddings = np.zeros((0, 512), dtype=np.float32)
        try:
            if self.roles_path.exists():
                self._roles = json.loads(self.roles_path.read_text(encoding="utf-8"))
                if not isinstance(self._roles, list):
                    self._roles = DEFAULT_ROLES.copy()
                elif not self._roles:
                    self._roles = DEFAULT_ROLES.copy()
                self._save_roles()
            else:
                self._roles = DEFAULT_ROLES.copy()
                self._save_roles()
        except Exception:
            self._roles = DEFAULT_ROLES.copy()
            try:
                self._save_roles()
            except Exception:
                pass

    def _save(self):
        self.meta_path.write_text(json.dumps(self._meta, indent=2), encoding="utf-8")
        self.ids_path.write_text(json.dumps(self._ids), encoding="utf-8")
        if self._embeddings is not None and self._embeddings.size > 0:
            np.save(self.embeddings_path, self._embeddings)

    def _save_roles(self):
        self.roles_path.write_text(json.dumps(self._roles, indent=2), encoding="utf-8")

    def get_roles(self) -> list[str]:
        """Return list of role names (including custom)."""
        return list(self._roles)

    def add_role(self, name: str) -> None:
        """Add a new role. Raises ValueError if empty or duplicate."""
        n = (name or "").strip()
        if not n:
            raise ValueError("Role name cannot be empty")
        if n in self._roles:
            raise ValueError("Role already exists")
        self._roles.append(n)
        self._save_roles()

    def delete_role(self, name: str) -> None:
        """Remove a role. Raises ValueError if role is in use by any face."""
        if name not in self._roles:
            raise ValueError("Role not found")
        count = sum(1 for mid in self._ids if self._meta.get(mid, {}).get("role") == name)
        if count > 0:
            raise ValueError(f"Cannot delete: {count} person(s) have this role. Reassign them first.")
        self._roles.remove(name)
        self._save_roles()

    def list_faces(self) -> list[dict]:
        """Return list of { identity_id, name, role, authorized } for all registered faces."""
        out = []
        for identity_id in self._ids:
            m = self._meta.get(identity_id, {})
            out.append({
                "identity_id": identity_id,
                "name": m.get("name", ""),
                "role": m.get("role", "Visitor"),
                "authorized": m.get("authorized", True),
            })
        return out

    def update_face(
        self,
        identity_id: str,
        name: str | None = None,
        role: str | None = None,
        authorized: bool | None = None,
    ) -> None:
        """Update name, role, and/or authorized for a registered face."""
        if identity_id not in self._meta:
            raise ValueError("Unknown identity_id")
        if name is not None:
            self._meta[identity_id]["name"] = name
        if role is not None:
            self._meta[identity_id]["role"] = role
        if authorized is not None:
            self._meta[identity_id]["authorized"] = authorized
        self._save()

    def delete_face(self, identity_id: str) -> None:
        """Remove a registered face from the database."""
        if identity_id not in self._ids:
            raise ValueError("Unknown identity_id")
        idx = self._ids.index(identity_id)
        self._ids.pop(idx)
        self._meta.pop(identity_id, None)
        if self._embeddings is not None and len(self._embeddings) > 0:
            self._embeddings = np.delete(self._embeddings, idx, axis=0)
            if self._embeddings.size == 0:
                self._embeddings = np.zeros((0, 512), dtype=np.float32)
        self._save()

    def _image_to_bgr(self, image_bytes: bytes) -> np.ndarray:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)  # fix rotation from phone/EXIF
        img = img.convert("RGB")
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    def _detect_faces(self, bgr: np.ndarray) -> list[tuple[list[float], np.ndarray]]:
        """Returns list of (bbox [x1,y1,x2,y2], bgr_crop). Tries DNN then Haar if needed."""
        h_img, w_img = bgr.shape[:2]
        # If image is huge, resize so face isn't tiny in the 300x300 DNN input
        max_side = 1200
        if max(h_img, w_img) > max_side:
            scale = max_side / max(h_img, w_img)
            new_w, new_h = int(w_img * scale), int(h_img * scale)
            bgr = cv2.resize(bgr, (new_w, new_h))
            h_img, w_img = bgr.shape[:2]

        def run_dnn():
            dnn = _get_detector_dnn(self.models_dir)
            if not isinstance(dnn, tuple):
                return []
            net, conf_thresh = dnn
            blob = cv2.dnn.blobFromImage(
                cv2.resize(bgr, (300, 300)), 1.0, (300, 300), (104.0, 177.0, 123.0)
            )
            net.setInput(blob)
            dets = net.forward()
            out = []
            for i in range(dets.shape[2]):
                conf = float(dets[0, 0, i, 2])
                if conf < conf_thresh:
                    continue
                x1 = int(dets[0, 0, i, 3] * w_img)
                y1 = int(dets[0, 0, i, 4] * h_img)
                x2 = int(dets[0, 0, i, 5] * w_img)
                y2 = int(dets[0, 0, i, 6] * h_img)
                x1, x2 = max(0, min(x1, x2)), max(x1, x2)
                y1, y2 = max(0, min(y1, y2)), max(y1, y2)
                if x2 <= x1 or y2 <= y1:
                    continue
                bbox = [float(x1), float(y1), float(x2), float(y2)]
                crop = bgr[y1:y2, x1:x2]
                out.append((bbox, crop))
            out.sort(key=lambda t: (t[0][2] - t[0][0]) * (t[0][3] - t[0][1]), reverse=True)
            return out

        def run_haar():
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            rects = _get_detector_haar().detectMultiScale(
                gray, scaleFactor=1.08, minNeighbors=4, minSize=(24, 24)
            )
            out = []
            for (x, y, w, h) in rects:
                bbox = _bbox_from_rect(x, y, w, h)
                crop = bgr[y : y + h, x : x + w]
                out.append((bbox, crop))
            out.sort(key=lambda t: (t[0][2] - t[0][0]) * (t[0][3] - t[0][1]), reverse=True)
            return out

        out = run_dnn()
        if not out:
            out = run_haar()
        return out

    def _embed(self, bgr_crop: np.ndarray) -> np.ndarray:
        sess, in_name, out_name = _get_arcface(self.models_dir)
        inp = _preprocess_face_crop(bgr_crop)
        out = sess.run([out_name], {in_name: inp})[0][0]
        norm = np.linalg.norm(out)
        if norm > 1e-10:
            out = out / norm
        return out.astype(np.float32)

    def register(self, image_bytes: bytes, name: str, role: str = "Visitor") -> tuple[str, str]:
        """Extract largest face, compute embedding, store. Returns (identity_id, message)."""
        bgr = self._image_to_bgr(image_bytes)
        faces = self._detect_faces(bgr)
        if not faces:
            raise ValueError("No face detected in image")
        bbox, crop = faces[0]
        emb = self._embed(crop)
        identity_id = str(uuid.uuid4())
        self._ids.append(identity_id)
        self._meta[identity_id] = {"name": name, "authorized": True, "role": role or "Visitor"}
        emb = emb.reshape(1, -1)
        if self._embeddings is None or self._embeddings.size == 0:
            self._embeddings = emb
        else:
            self._embeddings = np.vstack([self._embeddings, emb])
        self._save()
        return identity_id, f"Registered {name}"

    def recognize(self, image_bytes: bytes) -> list[dict]:
        """Detect faces, match to DB, return list of detections with bbox, identity, authorized."""
        bgr = self._image_to_bgr(image_bytes)
        faces = self._detect_faces(bgr)
        if not faces:
            return []
        detections = []
        threshold = RECOGNITION_THRESHOLD
        for bbox, crop in faces:
            try:
                emb = self._embed(crop)
            except Exception:
                detections.append({
                    "bbox": bbox,
                    "identity_id": None,
                    "name": None,
                    "role": None,
                    "authorized": False,
                    "score": 0.0,
                })
                continue
            emb = emb.reshape(1, -1)
            identity_id = None
            name = None
            role = None
            authorized = False
            score = 0.0
            if self._embeddings is not None and len(self._embeddings) > 0:
                norms = np.linalg.norm(self._embeddings, axis=1, keepdims=True)
                norms[norms == 0] = 1e-10
                embs_norm = self._embeddings / norms
                sim = (embs_norm @ emb.T).flatten()
                idx = int(np.argmax(sim))
                score = float(sim[idx])
                # Only accept if above threshold AND clearly better than second-best (avoids wrong person)
                margin_ok = True
                if len(sim) > 1:
                    sim_sorted = np.sort(sim)[::-1]
                    margin_ok = (sim_sorted[0] - sim_sorted[1]) >= RECOGNITION_MARGIN
                if score >= threshold and margin_ok:
                    identity_id = self._ids[idx]
                    meta = self._meta.get(identity_id, {})
                    name = meta.get("name")
                    role = meta.get("role", "Visitor")
                    authorized = meta.get("authorized", True)
            detections.append({
                "bbox": bbox,
                "identity_id": identity_id,
                "name": name,
                "role": role if identity_id else None,
                "authorized": authorized,
                "score": score,
            })
        return detections
