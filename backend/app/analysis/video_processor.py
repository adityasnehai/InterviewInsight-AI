import logging
import math
import os
from pathlib import Path

try:
    import cv2
except Exception:  # pragma: no cover - optional dependency
    cv2 = None

try:
    import mediapipe as mp
except Exception:  # pragma: no cover - optional dependency
    mp = None

try:
    import numpy as np
except Exception:  # pragma: no cover - optional dependency
    np = None

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional dependency
    Image = None

try:
    from transformers import pipeline
except Exception:  # pragma: no cover - optional dependency
    pipeline = None

LOGGER = logging.getLogger(__name__)
_MEDIAPIPE_UNAVAILABLE_LOGGED = False
_GLOBAL_EMOTION_RECOGNIZER = None

EMOTION_LABELS = ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]


class FacialEmotionRecognizer:
    """Emotion recognizer with pretrained model + deterministic heuristic fallback."""

    def __init__(self, model_name: str = "trpakov/vit-face-expression") -> None:
        self._model_name = model_name
        self._predictor = None
        self._disabled = os.getenv("IIA_DISABLE_MODEL_LOADING", "0") == "1"

    def _lazy_load(self) -> None:
        if self._predictor is not None or self._disabled:
            return
        if pipeline is None or Image is None:
            return
        try:
            self._predictor = pipeline("image-classification", model=self._model_name, top_k=None)
        except Exception as exc:  # pragma: no cover - model download/runtime failures
            LOGGER.warning("Falling back to heuristic emotion scoring: %s", exc)
            self._predictor = None

    def predict(self, frame_rgb) -> dict[str, float]:
        self._lazy_load()
        if self._predictor is None or Image is None:
            return _heuristic_emotion_scores(frame_rgb)
        try:
            preds = self._predictor(Image.fromarray(frame_rgb))
            return _normalize_emotions(preds)
        except Exception as exc:  # pragma: no cover
            LOGGER.warning("Emotion model inference failed, using heuristic: %s", exc)
            return _heuristic_emotion_scores(frame_rgb)


def process_video(video_file_path: str, target_fps: int = 3) -> list[dict]:
    """Extract time-indexed facial and gaze features from video frames."""
    path = Path(video_file_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Video file not found: {path}")

    if cv2 is None:
        # Keep pipeline operational even when OpenCV is unavailable.
        return [
            {
                "timestamp": 0.0,
                "facial_emotion_scores": _default_emotions(),
                "head_pose": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
                "gaze_direction": "unknown",
                "eye_contact": 0.0,
            }
        ]

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"Unable to open video: {path}")

    native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    target_fps = max(1, int(target_fps))
    frame_interval = max(1, int(round(native_fps / target_fps)))

    face_mesh = _build_face_mesh()
    emotion_model = _get_emotion_recognizer()
    frame_index = 0
    features: list[dict] = []

    while True:
        ok, frame_bgr = cap.read()
        if not ok:
            break

        if frame_index % frame_interval != 0:
            frame_index += 1
            continue

        timestamp = frame_index / native_fps
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        landmark_data = _extract_landmark_features(frame_rgb, face_mesh)
        feature = {
            "timestamp": float(timestamp),
            "facial_emotion_scores": emotion_model.predict(frame_rgb),
            "head_pose": landmark_data["head_pose"],
            "gaze_direction": landmark_data["gaze_direction"],
            "eye_contact": landmark_data["eye_contact"],
        }
        features.append(feature)
        frame_index += 1

    cap.release()
    if face_mesh is not None:
        face_mesh.close()

    if not features:
        features.append(
            {
                "timestamp": 0.0,
                "facial_emotion_scores": _default_emotions(),
                "head_pose": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
                "gaze_direction": "unknown",
                "eye_contact": 0.0,
            }
        )
    return features


def _build_face_mesh():
    global _MEDIAPIPE_UNAVAILABLE_LOGGED
    if mp is None:
        if not _MEDIAPIPE_UNAVAILABLE_LOGGED:
            LOGGER.info("MediaPipe is not installed; using landmark fallback mode.")
            _MEDIAPIPE_UNAVAILABLE_LOGGED = True
        return None
    solutions = getattr(mp, "solutions", None)
    if solutions is None:
        if not _MEDIAPIPE_UNAVAILABLE_LOGGED:
            LOGGER.info("MediaPipe solutions API is unavailable; using landmark fallback mode.")
            _MEDIAPIPE_UNAVAILABLE_LOGGED = True
        return None
    try:
        return solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
    except Exception as exc:  # pragma: no cover
        if not _MEDIAPIPE_UNAVAILABLE_LOGGED:
            LOGGER.warning("MediaPipe FaceMesh unavailable; using fallback mode: %s", exc)
            _MEDIAPIPE_UNAVAILABLE_LOGGED = True
        return None


def _get_emotion_recognizer() -> FacialEmotionRecognizer:
    global _GLOBAL_EMOTION_RECOGNIZER
    if _GLOBAL_EMOTION_RECOGNIZER is None:
        _GLOBAL_EMOTION_RECOGNIZER = FacialEmotionRecognizer()
    return _GLOBAL_EMOTION_RECOGNIZER


def _extract_landmark_features(frame_rgb, face_mesh) -> dict:
    if face_mesh is None:
        return {
            "head_pose": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            "gaze_direction": "unknown",
            "eye_contact": 0.0,
        }

    result = face_mesh.process(frame_rgb)
    if not result.multi_face_landmarks:
        return {
            "head_pose": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            "gaze_direction": "unknown",
            "eye_contact": 0.0,
        }

    landmarks = result.multi_face_landmarks[0].landmark
    nose = landmarks[1]
    left_eye = landmarks[33]
    right_eye = landmarks[263]
    forehead = landmarks[10]
    chin = landmarks[152]

    eye_mid_x = (left_eye.x + right_eye.x) / 2.0
    eye_mid_y = (left_eye.y + right_eye.y) / 2.0

    yaw = float((nose.x - eye_mid_x) * 100.0)
    pitch = float(((nose.y - eye_mid_y) - (chin.y - forehead.y) * 0.25) * 100.0)
    roll = float(math.degrees(math.atan2(right_eye.y - left_eye.y, right_eye.x - left_eye.x)))

    gaze_offset = nose.x - eye_mid_x
    if abs(gaze_offset) <= 0.01:
        gaze_direction = "center"
    elif gaze_offset > 0:
        gaze_direction = "right"
    else:
        gaze_direction = "left"

    return {
        "head_pose": {"yaw": yaw, "pitch": pitch, "roll": roll},
        "gaze_direction": gaze_direction,
        "eye_contact": 1.0 if gaze_direction == "center" else 0.0,
    }


def _normalize_emotions(preds: list[dict]) -> dict[str, float]:
    scores = _default_emotions()
    for pred in preds:
        label = str(pred.get("label", "")).strip().lower()
        score = float(pred.get("score", 0.0))
        if label in scores:
            scores[label] = score
    total = sum(scores.values())
    if total <= 0:
        return _default_emotions()
    return {label: value / total for label, value in scores.items()}


def _heuristic_emotion_scores(frame_rgb) -> dict[str, float]:
    scores = _default_emotions()
    if np is None:
        return scores

    brightness = float(np.mean(frame_rgb) / 255.0)
    contrast = float(np.std(frame_rgb) / 255.0)

    scores["neutral"] = max(0.2, 1.0 - contrast)
    scores["happy"] = max(0.05, brightness * 0.6)
    scores["sad"] = max(0.05, (1.0 - brightness) * 0.5)
    scores["surprise"] = max(0.05, contrast * 0.7)
    scores["angry"] = max(0.05, contrast * 0.4)
    scores["fear"] = max(0.05, contrast * 0.3)
    scores["disgust"] = 0.05

    total = sum(scores.values())
    return {label: value / total for label, value in scores.items()}


def _default_emotions() -> dict[str, float]:
    base = 1.0 / len(EMOTION_LABELS)
    return {label: base for label in EMOTION_LABELS}
