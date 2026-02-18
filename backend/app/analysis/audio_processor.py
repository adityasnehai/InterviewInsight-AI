import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    import librosa
except Exception:  # pragma: no cover - optional dependency
    librosa = None

try:
    import numpy as np
except Exception:  # pragma: no cover - optional dependency
    np = None

try:
    import whisper
except Exception:  # pragma: no cover - optional dependency
    whisper = None

try:
    from transformers import pipeline
except Exception:  # pragma: no cover - optional dependency
    pipeline = None

LOGGER = logging.getLogger(__name__)
_FFMPEG_UNAVAILABLE_LOGGED = False
_WHISPER_MODEL_CACHE: dict[str, object | None] = {}
_SPEECH_EMOTION_CLASSIFIER = None
_SPEECH_EMOTION_INITIALIZED = False


def process_audio(video_file_path: str | None = None, audio_file_path: str | None = None) -> dict:
    """Transcribe audio and extract acoustic/prosodic features."""
    resolved_audio_path = _resolve_audio_path(video_file_path=video_file_path, audio_file_path=audio_file_path)
    transcript_text, transcript_segments = _run_transcription(resolved_audio_path)
    speech_features = _extract_speech_features(resolved_audio_path, transcript_text, transcript_segments)
    segment_emotions = _speech_emotion_scores(resolved_audio_path)
    segment_features = _build_segment_features(transcript_segments, speech_features, segment_emotions)

    return {
        "audio_file_path": resolved_audio_path,
        "transcript_text": transcript_text,
        "transcript_segments": transcript_segments,
        "speech_features": speech_features,
        "segment_features": segment_features,
    }


def _resolve_audio_path(video_file_path: str | None, audio_file_path: str | None) -> str | None:
    if audio_file_path:
        path = Path(audio_file_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")
        return str(path)

    if video_file_path:
        return _extract_audio_from_video(video_file_path)
    return None


def _extract_audio_from_video(video_file_path: str) -> str | None:
    global _FFMPEG_UNAVAILABLE_LOGGED
    video_path = Path(video_file_path).expanduser()
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found for audio extraction: {video_path}")

    if shutil.which("ffmpeg") is None:
        if not _FFMPEG_UNAVAILABLE_LOGGED:
            LOGGER.info("ffmpeg not found on PATH; skipping audio extraction from video.")
            _FFMPEG_UNAVAILABLE_LOGGED = True
        return None

    out_file = tempfile.NamedTemporaryFile(suffix=".wav", prefix="iia_audio_", delete=False)
    out_file.close()
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        out_file.name,
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return out_file.name
    except Exception as exc:  # pragma: no cover - ffmpeg may not exist
        LOGGER.warning("Audio extraction failed; continuing without extracted audio: %s", exc)
        Path(out_file.name).unlink(missing_ok=True)
        return None


def _run_transcription(audio_file_path: str | None) -> tuple[str, list[dict]]:
    if audio_file_path is None:
        return "", []

    model = _get_whisper_model()
    if model is None:
        fallback = "Automatic transcription unavailable in lightweight mode."
        return fallback, [{"start": 0.0, "end": 0.0, "text": fallback}]

    try:
        result = model.transcribe(audio_file_path, fp16=False)
        segments = [
            {
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
                "text": str(seg.get("text", "")).strip(),
            }
            for seg in result.get("segments", [])
        ]
        transcript_text = str(result.get("text", "")).strip()
        if not segments and transcript_text:
            segments = [{"start": 0.0, "end": 0.0, "text": transcript_text}]
        return transcript_text, segments
    except Exception as exc:  # pragma: no cover - model runtime/download failures
        LOGGER.warning("Whisper transcription failed; using fallback transcript: %s", exc)
        fallback = "Automatic transcription failed; fallback transcript used."
        return fallback, [{"start": 0.0, "end": 0.0, "text": fallback}]


def _get_whisper_model():
    model_disabled = os.getenv("IIA_DISABLE_MODEL_LOADING", "0") == "1"
    if whisper is None or model_disabled:
        return None

    model_name = (os.getenv("IIA_WHISPER_MODEL", "tiny") or "tiny").strip()
    if model_name in _WHISPER_MODEL_CACHE:
        return _WHISPER_MODEL_CACHE[model_name]

    try:
        model = whisper.load_model(model_name)
        _WHISPER_MODEL_CACHE[model_name] = model
        return model
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("Unable to load Whisper model '%s'; using fallback transcript: %s", model_name, exc)
        _WHISPER_MODEL_CACHE[model_name] = None
        return None


def _extract_speech_features(
    audio_file_path: str | None,
    transcript_text: str,
    transcript_segments: list[dict],
) -> dict:
    base_features = {
        "pitch": 0.0,
        "pause_durations": [],
        "speaking_rate": 0.0,
        "prosody": {
            "log_mel_mean": 0.0,
            "log_mel_std": 0.0,
            "mfcc_mean": 0.0,
            "mfcc_std": 0.0,
        },
        "duration_seconds": 0.0,
    }

    if audio_file_path is None or librosa is None or np is None:
        return base_features

    try:
        y, sr = librosa.load(audio_file_path, sr=16000)
        if y.size == 0:
            return base_features

        duration_seconds = float(librosa.get_duration(y=y, sr=sr))
        pitch = _estimate_pitch(y, sr)
        pause_durations = _compute_pause_durations(transcript_segments)
        speaking_rate = _estimate_speaking_rate(transcript_text, duration_seconds)

        mel = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=40)
        log_mel = librosa.power_to_db(mel, ref=np.max)
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)

        return {
            "pitch": pitch,
            "pause_durations": pause_durations,
            "speaking_rate": speaking_rate,
            "prosody": {
                "log_mel_mean": float(np.mean(log_mel)),
                "log_mel_std": float(np.std(log_mel)),
                "mfcc_mean": float(np.mean(mfcc)),
                "mfcc_std": float(np.std(mfcc)),
            },
            "duration_seconds": duration_seconds,
        }
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("Audio feature extraction failed; using defaults: %s", exc)
        return base_features


def _estimate_pitch(y, sr: int) -> float:
    if librosa is None or np is None:
        return 0.0
    try:
        f0, _, _ = librosa.pyin(y, fmin=60, fmax=400, sr=sr)
        valid = f0[~np.isnan(f0)]
        if valid.size == 0:
            return 0.0
        return float(np.mean(valid))
    except Exception:
        return 0.0


def _estimate_speaking_rate(transcript_text: str, duration_seconds: float) -> float:
    if duration_seconds <= 0:
        return 0.0
    words = transcript_text.split()
    return float(len(words) / duration_seconds * 60.0)


def _compute_pause_durations(transcript_segments: list[dict]) -> list[float]:
    if len(transcript_segments) <= 1:
        return []
    pauses: list[float] = []
    previous_end = float(transcript_segments[0].get("end", 0.0))
    for segment in transcript_segments[1:]:
        start = float(segment.get("start", previous_end))
        pause = max(0.0, start - previous_end)
        pauses.append(pause)
        previous_end = float(segment.get("end", start))
    return pauses


def _speech_emotion_scores(audio_file_path: str | None) -> dict[str, float]:
    labels = {"calm": 0.4, "happy": 0.2, "sad": 0.1, "angry": 0.1, "neutral": 0.2}
    if audio_file_path is None:
        return labels
    classifier = _get_speech_emotion_classifier()
    if classifier is None:
        return labels

    try:
        preds = classifier(audio_file_path)
        out = {str(item["label"]).lower(): float(item["score"]) for item in preds}
        total = sum(out.values())
        if total <= 0:
            return labels
        return {k: v / total for k, v in out.items()}
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("Speech emotion inference failed; using fallback scores: %s", exc)
        return labels


def _get_speech_emotion_classifier():
    global _SPEECH_EMOTION_CLASSIFIER, _SPEECH_EMOTION_INITIALIZED
    if _SPEECH_EMOTION_INITIALIZED:
        return _SPEECH_EMOTION_CLASSIFIER
    _SPEECH_EMOTION_INITIALIZED = True

    if pipeline is None or os.getenv("IIA_DISABLE_MODEL_LOADING", "0") == "1":
        _SPEECH_EMOTION_CLASSIFIER = None
        return None
    try:
        _SPEECH_EMOTION_CLASSIFIER = pipeline("audio-classification", model="superb/hubert-large-superb-er", top_k=5)
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("Speech emotion model unavailable; using fallback scores: %s", exc)
        _SPEECH_EMOTION_CLASSIFIER = None
    return _SPEECH_EMOTION_CLASSIFIER


def _build_segment_features(
    transcript_segments: list[dict],
    speech_features: dict,
    emotion_scores: dict[str, float],
) -> list[dict]:
    pauses = speech_features.get("pause_durations", [])
    speaking_rate = float(speech_features.get("speaking_rate", 0.0))
    pitch = float(speech_features.get("pitch", 0.0))
    prosody = speech_features.get("prosody", {})

    segment_features: list[dict] = []
    for idx, segment in enumerate(transcript_segments):
        segment_features.append(
            {
                "start": float(segment.get("start", 0.0)),
                "end": float(segment.get("end", 0.0)),
                "text": str(segment.get("text", "")),
                "pitch": pitch,
                "pause_duration": float(pauses[idx - 1]) if idx > 0 and idx - 1 < len(pauses) else 0.0,
                "speaking_rate": speaking_rate,
                "prosody": {
                    "log_mel_mean": float(prosody.get("log_mel_mean", 0.0)),
                    "log_mel_std": float(prosody.get("log_mel_std", 0.0)),
                    "mfcc_mean": float(prosody.get("mfcc_mean", 0.0)),
                    "mfcc_std": float(prosody.get("mfcc_std", 0.0)),
                },
                "speech_emotion_scores": emotion_scores,
            }
        )
    return segment_features
