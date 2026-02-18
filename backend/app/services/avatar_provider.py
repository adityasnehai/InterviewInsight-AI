import json
import os
import re
import threading
import urllib.error
import urllib.request
import wave
import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

STORAGE_ROOT = Path(__file__).resolve().parents[1] / "storage"


@dataclass
class AvatarProviderConfig:
    enabled: bool
    provider: str
    mode: str
    message: str


class AvatarProviderService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._virtual_requests: dict[str, dict] = {}
        self._simli_requests: dict[str, dict] = {}
        self._request_audio_paths: dict[str, Path] = {}
        self._avatar_audio_dir = STORAGE_ROOT / "avatar_audio"
        self._avatar_audio_dir.mkdir(parents=True, exist_ok=True)

    def get_config(self) -> AvatarProviderConfig:
        mode = os.getenv("IIA_AVATAR_MODE", "browser").strip().lower()
        provider = os.getenv("IIA_AVATAR_PROVIDER", "browser").strip().lower()

        if mode in {"virtual3d", "virtual_human_3d"}:
            if not os.getenv("OPENAI_API_KEY", "").strip():
                return AvatarProviderConfig(
                    enabled=False,
                    provider="browser",
                    mode="browser_tts",
                    message="Set OPENAI_API_KEY to enable 3D virtual human voice + lip sync.",
                )
            return AvatarProviderConfig(
                enabled=True,
                provider="virtual3d",
                mode="virtual_human_3d",
                message="3D virtual human mode enabled (audio + visemes).",
            )

        if mode != "provider":
            return AvatarProviderConfig(
                enabled=False,
                provider="browser",
                mode="browser_tts",
                message="Provider avatar disabled. Using browser TTS avatar.",
            )

        if provider not in {"did", "heygen", "simli"}:
            return AvatarProviderConfig(
                enabled=False,
                provider="browser",
                mode="browser_tts",
                message="Unknown provider configured. Use did, heygen, or simli.",
            )

        api_key = os.getenv("IIA_AVATAR_API_KEY", "").strip()
        if not api_key:
            return AvatarProviderConfig(
                enabled=False,
                provider="browser",
                mode="browser_tts",
                message="Avatar provider key missing. Set IIA_AVATAR_API_KEY.",
            )

        return AvatarProviderConfig(
            enabled=True,
            provider=provider,
            mode="provider",
            message=f"{provider} avatar provider is enabled.",
        )

    def synthesize_avatar_prompt(
        self,
        text: str,
        session_id: str | None = None,
    ) -> dict:
        config = self.get_config()
        if not config.enabled:
            return {
                "mode": "browser_tts",
                "provider": "browser",
                "text": text,
                "warnings": [],
                "fallbackReason": config.message,
            }

        try:
            if config.provider == "virtual3d":
                return self._build_virtual_human_response(text=text, session_id=session_id)
            if config.provider == "did":
                return self._call_did(text=text, session_id=session_id)
            if config.provider == "heygen":
                return self._call_heygen(text=text, session_id=session_id)
            if config.provider == "simli":
                return self._call_simli(text=text, session_id=session_id)
        except Exception as exc:
            return {
                "mode": "browser_tts",
                "provider": "browser",
                "text": text,
                "providerPayload": None,
                "warnings": [f"Provider call failed: {exc}"],
                "fallbackReason": "Provider request failed, browser TTS fallback used.",
            }

        return {
            "mode": "browser_tts",
            "provider": "browser",
            "text": text,
            "providerPayload": None,
            "warnings": [],
            "fallbackReason": "Unsupported provider mode.",
        }

    def get_render_status(self, request_id: str, provider: str | None = None) -> dict:
        config = self.get_config()
        effective_provider = (provider or config.provider).strip().lower()
        if effective_provider == "browser":
            return {
                "provider": "browser",
                "requestId": request_id,
                "status": "ready",
                "isReady": True,
                "videoUrl": None,
                "audioUrl": None,
                "emotion": None,
                "speakingStyle": None,
                "visemeTimeline": [],
                "providerPayload": None,
                "error": None,
            }
        if effective_provider == "virtual3d":
            return self._get_virtual3d_status(request_id=request_id)
        if effective_provider == "simli":
            return self._get_simli_status(request_id=request_id)

        if not config.enabled:
            return {
                "provider": "browser",
                "requestId": request_id,
                "status": "fallback",
                "isReady": False,
                "videoUrl": None,
                "audioUrl": None,
                "emotion": None,
                "speakingStyle": None,
                "visemeTimeline": [],
                "providerPayload": None,
                "error": config.message,
            }

        try:
            if effective_provider == "did":
                return self._get_did_status(request_id=request_id)
            if effective_provider == "heygen":
                return self._get_heygen_status(request_id=request_id)
        except Exception as exc:
            return {
                "provider": effective_provider,
                "requestId": request_id,
                "status": "error",
                "isReady": False,
                "videoUrl": None,
                "audioUrl": None,
                "emotion": None,
                "speakingStyle": None,
                "visemeTimeline": [],
                "providerPayload": None,
                "error": str(exc),
            }

        return {
            "provider": effective_provider or "unknown",
            "requestId": request_id,
            "status": "error",
            "isReady": False,
            "videoUrl": None,
            "audioUrl": None,
            "emotion": None,
            "speakingStyle": None,
            "visemeTimeline": [],
            "providerPayload": None,
            "error": "Unsupported provider",
        }

    @staticmethod
    def get_local_asset_path(request_id: str) -> Path | None:
        _ = request_id
        return None

    def get_local_audio_path(self, request_id: str) -> Path | None:
        with self._lock:
            mapped = self._request_audio_paths.get(request_id)
        if mapped and mapped.exists():
            return mapped
        audio_path = self._avatar_audio_dir / f"{request_id}.wav"
        if audio_path.exists():
            return audio_path
        return None

    def _build_virtual_human_response(self, text: str, session_id: str | None = None) -> dict:
        request_id = str(uuid4())
        emotion, speaking_style = self._infer_emotion_and_style(text)
        audio_path = self._get_or_create_cached_tts_audio(text=text, style_hint=speaking_style)
        if audio_path is None:
            return {
                "mode": "browser_tts",
                "provider": "browser",
                "text": text,
                "providerPayload": None,
                "warnings": ["OpenAI TTS failed for virtual3d mode."],
                "fallbackReason": "Virtual human TTS failed; browser TTS fallback used.",
            }

        duration_seconds = self._estimate_audio_duration_seconds(audio_path)
        viseme_timeline = self._build_viseme_timeline(text=text, duration_seconds=duration_seconds)
        audio_url = self._build_local_audio_url(request_id)
        status_url = self._build_status_url(request_id=request_id, provider="virtual3d")
        payload = {
            "provider": "virtual3d",
            "requestId": request_id,
            "status": "ready",
            "isReady": True,
            "videoUrl": None,
            "audioUrl": audio_url,
            "emotion": emotion,
            "speakingStyle": speaking_style,
            "visemeTimeline": viseme_timeline,
            "providerPayload": None,
            "error": None,
            "sessionId": session_id,
        }
        with self._lock:
            self._virtual_requests[request_id] = dict(payload)
            self._request_audio_paths[request_id] = audio_path

        return {
            "mode": "virtual_human_3d",
            "provider": "virtual3d",
            "text": text,
            "requestId": request_id,
            "videoUrl": None,
            "audioUrl": audio_url,
            "statusUrl": status_url,
            "emotion": emotion,
            "speakingStyle": speaking_style,
            "visemeTimeline": viseme_timeline,
            "providerPayload": None,
            "warnings": [],
            "fallbackReason": None,
        }

    def _get_virtual3d_status(self, request_id: str) -> dict:
        with self._lock:
            payload = self._virtual_requests.get(request_id)
        if payload is None:
            return {
                "provider": "virtual3d",
                "requestId": request_id,
                "status": "not_found",
                "isReady": False,
                "videoUrl": None,
                "audioUrl": None,
                "emotion": None,
                "speakingStyle": None,
                "visemeTimeline": [],
                "providerPayload": None,
                "error": "Unknown request ID.",
            }
        return {
            "provider": str(payload.get("provider", "virtual3d")),
            "requestId": request_id,
            "status": str(payload.get("status", "ready")),
            "isReady": bool(payload.get("isReady", True)),
            "videoUrl": payload.get("videoUrl"),
            "audioUrl": payload.get("audioUrl"),
            "emotion": payload.get("emotion"),
            "speakingStyle": payload.get("speakingStyle"),
            "visemeTimeline": payload.get("visemeTimeline") or [],
            "providerPayload": payload.get("providerPayload"),
            "error": payload.get("error"),
        }

    def _call_simli(self, text: str, session_id: str | None = None) -> dict:
        api_key = os.getenv("IIA_AVATAR_API_KEY", "").strip()
        base_url = os.getenv("IIA_AVATAR_BASE_URL", "https://api.simli.ai").strip().rstrip("/")
        face_id = os.getenv("IIA_SIMLI_FACE_ID", "").strip()
        max_session_length = int(os.getenv("IIA_SIMLI_MAX_SESSION_LENGTH", "3600"))
        max_idle_time = int(os.getenv("IIA_SIMLI_MAX_IDLE_TIME", "300"))

        if not face_id:
            raise ValueError("IIA_SIMLI_FACE_ID is required for Simli provider.")

        request_id = str(uuid4())
        warnings: list[str] = []

        # Simli auth/session bootstrap.
        session_payload: dict = {
            "apiKey": api_key,
            "faceId": face_id,
        }
        session_response = _post_json(
            url=f"{base_url}/startAudioToVideoSession",
            payload=session_payload,
            headers={
                "Content-Type": "application/json",
            },
        )
        session_token = self._extract_first(
            session_response,
            "session_token",
            "sessionToken",
            "token",
            "accessToken",
        )
        if not session_token:
            raise RuntimeError("Simli did not return a session token.")
        video_url = self._extract_first_url(session_response)

        ice_servers: list[dict] = []
        try:
            ice_response = _post_json(
                url=f"{base_url}/getIceServer",
                payload={"apiKey": api_key},
                headers={"Content-Type": "application/json"},
            )
            ice_servers = self._extract_ice_servers(ice_response)
        except Exception:
            try:
                ice_response = _post_json(
                    url=f"{base_url}/getIceServers",
                    payload={"apiKey": api_key},
                    headers={"Content-Type": "application/json"},
                )
                ice_servers = self._extract_ice_servers(ice_response)
            except Exception:
                warnings.append("Could not fetch Simli ICE servers from API.")

        audio_url = None
        audio_path = self._get_or_create_cached_tts_audio(text=text, style_hint="professional_calm")
        if audio_path is not None:
            audio_url = self._build_local_audio_url(request_id)
            with self._lock:
                self._request_audio_paths[request_id] = audio_path
        else:
            warnings.append("OpenAI TTS failed; Simli session is ready but no generated question audio available.")

        provider_payload = {
            "faceId": face_id,
            "sessionToken": session_token,
            "iceServers": ice_servers,
            "maxSessionLength": max_session_length,
            "maxIdleTime": max_idle_time,
        }
        status_url = None

        status_payload = {
            "provider": "simli",
            "requestId": request_id,
            "status": "ready",
            "isReady": True,
            "videoUrl": video_url,
            "audioUrl": audio_url,
            "emotion": "neutral",
            "speakingStyle": "professional_calm",
            "visemeTimeline": [],
            "providerPayload": provider_payload,
            "error": None,
            "sessionId": session_id,
        }
        with self._lock:
            self._simli_requests[request_id] = dict(status_payload)

        return {
            "mode": "provider",
            "provider": "simli",
            "text": text,
            "requestId": request_id,
            "videoUrl": video_url,
            "audioUrl": audio_url,
            "statusUrl": status_url,
            "emotion": "neutral",
            "speakingStyle": "professional_calm",
            "visemeTimeline": [],
            "providerPayload": provider_payload,
            "warnings": warnings,
            "fallbackReason": None,
        }

    def _get_simli_status(self, request_id: str) -> dict:
        with self._lock:
            payload = self._simli_requests.get(request_id)
        if payload is None:
            return {
                "provider": "simli",
                "requestId": request_id,
                "status": "not_found",
                "isReady": False,
                "videoUrl": None,
                "audioUrl": None,
                "emotion": None,
                "speakingStyle": None,
                "visemeTimeline": [],
                "providerPayload": None,
                "error": "Unknown request ID.",
            }

        return {
            "provider": "simli",
            "requestId": request_id,
            "status": str(payload.get("status", "ready")),
            "isReady": bool(payload.get("isReady", True)),
            "videoUrl": payload.get("videoUrl"),
            "audioUrl": payload.get("audioUrl"),
            "emotion": payload.get("emotion"),
            "speakingStyle": payload.get("speakingStyle"),
            "visemeTimeline": payload.get("visemeTimeline") or [],
            "providerPayload": payload.get("providerPayload"),
            "error": payload.get("error"),
        }

    @staticmethod
    def _extract_first(source: dict, *keys: str) -> str:
        for key in keys:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        data = source.get("data")
        if isinstance(data, dict):
            for key in keys:
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

    @staticmethod
    def _extract_ice_servers(source: dict) -> list[dict]:
        for key in ("iceServers", "ice_servers", "iceServer", "ice_server"):
            value = source.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                return [value]
        data = source.get("data")
        if isinstance(data, dict):
            for key in ("iceServers", "ice_servers", "iceServer", "ice_server"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
                if isinstance(value, dict):
                    return [value]
        return []

    @staticmethod
    def _extract_first_url(source: dict) -> str | None:
        def walk(value):
            if isinstance(value, str):
                trimmed = value.strip()
                if trimmed.startswith("http://") or trimmed.startswith("https://"):
                    return trimmed
                return None
            if isinstance(value, list):
                for item in value:
                    found = walk(item)
                    if found:
                        return found
                return None
            if isinstance(value, dict):
                preferred_keys = (
                    "videoUrl",
                    "video_url",
                    "streamUrl",
                    "stream_url",
                    "hlsUrl",
                    "hls_url",
                    "result_url",
                    "url",
                )
                for key in preferred_keys:
                    if key in value:
                        found = walk(value.get(key))
                        if found:
                            return found
                for nested in value.values():
                    found = walk(nested)
                    if found:
                        return found
            return None

        return walk(source)

    @staticmethod
    def _infer_emotion_and_style(text: str) -> tuple[str, str]:
        content = text.lower()
        if any(token in content for token in ("great", "excited", "welcome", "awesome")):
            return "encouraging", "warm_confident"
        if any(token in content for token in ("challenge", "tradeoff", "risk", "failure")):
            return "serious", "focused_professional"
        if any(token in content for token in ("explain", "describe", "walk me through", "how")):
            return "neutral", "clear_instructional"
        return "neutral", "professional_calm"

    @staticmethod
    def _build_viseme_timeline(text: str, duration_seconds: float) -> list[dict]:
        words = re.findall(r"[A-Za-z']+", text)
        if not words:
            return []

        timeline: list[dict] = []
        total_words = max(len(words), 1)
        word_duration = max(duration_seconds / total_words, 0.1)
        cursor = 0.0

        vowel_map = {
            "a": "A",
            "e": "E",
            "i": "I",
            "o": "O",
            "u": "U",
            "y": "I",
        }

        for word in words:
            word_lower = word.lower()
            dominant = "rest"
            for char in word_lower:
                if char in vowel_map:
                    dominant = vowel_map[char]
                    break

            start = round(cursor, 3)
            end = round(min(cursor + word_duration, duration_seconds), 3)
            timeline.append(
                {
                    "start": start,
                    "end": end,
                    "viseme": dominant,
                    "intensity": 0.85 if dominant != "rest" else 0.2,
                }
            )
            cursor += word_duration

        return timeline

    @staticmethod
    def _estimate_audio_duration_seconds(audio_path: Path) -> float:
        try:
            with wave.open(str(audio_path), "rb") as wav_file:
                frame_count = wav_file.getnframes()
                frame_rate = wav_file.getframerate()
                if frame_rate <= 0:
                    return 2.0
                return max(frame_count / frame_rate, 0.5)
        except Exception:
            return 2.0

    @staticmethod
    def _synthesize_openai_tts(text: str, output_path: Path, style_hint: str | None = None) -> bool:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return False

        model = os.getenv("IIA_VIRTUAL_AVATAR_TTS_MODEL", "gpt-4o-mini-tts").strip() or "gpt-4o-mini-tts"
        voice = os.getenv("IIA_VIRTUAL_AVATAR_VOICE", "alloy").strip() or "alloy"
        instructions = None
        if style_hint:
            instructions = (
                "Read this as an interview coach. Keep pacing natural and clear. "
                f"Style hint: {style_hint}."
            )

        try:
            from openai import OpenAI  # type: ignore

            client = OpenAI(api_key=api_key)
            response = None

            for format_key in ("response_format", "format", "audio_format"):
                try:
                    kwargs = {
                        "model": model,
                        "voice": voice,
                        "input": text,
                        format_key: "wav",
                    }
                    if instructions:
                        kwargs["instructions"] = instructions
                    response = client.audio.speech.create(**kwargs)
                    break
                except TypeError:
                    continue

            if response is None:
                return False

            if hasattr(response, "stream_to_file"):
                response.stream_to_file(str(output_path))
            elif hasattr(response, "read"):
                output_path.write_bytes(response.read())  # type: ignore[arg-type]
            elif hasattr(response, "content"):
                content = response.content  # type: ignore[attr-defined]
                if isinstance(content, (bytes, bytearray)):
                    output_path.write_bytes(bytes(content))
                else:
                    return False
            else:
                return False

            return output_path.exists() and output_path.stat().st_size > 0
        except Exception:
            return False

    def _get_or_create_cached_tts_audio(self, text: str, style_hint: str | None = None) -> Path | None:
        normalized_text = re.sub(r"\s+", " ", str(text or "").strip().lower())
        cache_material = f"{style_hint or 'default'}::{normalized_text}"
        cache_key = hashlib.sha256(cache_material.encode("utf-8")).hexdigest()[:20]
        cache_path = self._avatar_audio_dir / f"cache_{cache_key}.wav"
        if cache_path.exists() and cache_path.stat().st_size > 0:
            return cache_path
        if self._synthesize_openai_tts(text=text, output_path=cache_path, style_hint=style_hint):
            return cache_path
        return None

    @staticmethod
    def _build_local_audio_url(request_id: str) -> str:
        base_url = os.getenv("IIA_BACKEND_BASE_URL", "http://localhost:8000").strip().rstrip("/")
        return f"{base_url}/app/live/avatar/audio/{request_id}"

    @staticmethod
    def _build_status_url(request_id: str, provider: str) -> str:
        base_url = os.getenv("IIA_BACKEND_BASE_URL", "http://localhost:8000").strip().rstrip("/")
        return f"{base_url}/app/live/avatar/status?requestId={request_id}&provider={provider}"

    def _call_did(self, text: str, session_id: str | None = None) -> dict:
        api_key = os.getenv("IIA_AVATAR_API_KEY", "").strip()
        base_url = os.getenv("IIA_AVATAR_BASE_URL", "https://api.d-id.com").strip().rstrip("/")
        source_url = os.getenv("IIA_DID_SOURCE_URL", "").strip()
        voice_id = os.getenv("IIA_DID_VOICE_ID", "").strip()

        if not source_url:
            raise ValueError("IIA_DID_SOURCE_URL is required for D-ID provider.")

        script_payload: dict = {
            "type": "text",
            "input": text,
        }
        if voice_id:
            script_payload["provider"] = {
                "type": "microsoft",
                "voice_id": voice_id,
            }

        payload = {
            "script": script_payload,
            "source_url": source_url,
        }
        if session_id:
            payload["metadata"] = {"session_id": session_id}

        response = _post_json(
            url=f"{base_url}/talks",
            payload=payload,
            headers={
                "Authorization": f"Basic {api_key}" if not api_key.lower().startswith("basic ") else api_key,
                "Content-Type": "application/json",
            },
        )

        request_id = str(response.get("id", "")).strip() or None
        status_url = (
            str(response.get("status_url", "")).strip()
            or (f"{base_url}/talks/{request_id}" if request_id else None)
        )
        video_url = str(response.get("result_url", "")).strip() or str(response.get("video_url", "")).strip() or None

        return {
            "mode": "provider",
            "provider": "did",
            "text": text,
            "requestId": request_id,
            "videoUrl": video_url,
            "audioUrl": None,
            "statusUrl": status_url,
            "emotion": None,
            "speakingStyle": None,
            "visemeTimeline": [],
            "warnings": [] if video_url else ["D-ID accepted request. Poll statusUrl until the video is ready."],
            "fallbackReason": None,
        }

    def _call_heygen(self, text: str, session_id: str | None = None) -> dict:
        api_key = os.getenv("IIA_AVATAR_API_KEY", "").strip()
        base_url = os.getenv("IIA_AVATAR_BASE_URL", "https://api.heygen.com").strip().rstrip("/")
        avatar_id = os.getenv("IIA_HEYGEN_AVATAR_ID", "").strip()
        voice_id = os.getenv("IIA_HEYGEN_VOICE_ID", "").strip()

        if not avatar_id:
            raise ValueError("IIA_HEYGEN_AVATAR_ID is required for HeyGen provider.")

        payload = {
            "video_inputs": [
                {
                    "character": {
                        "type": "avatar",
                        "avatar_id": avatar_id,
                    },
                    "voice": {
                        "type": "text",
                        "input_text": text,
                    },
                }
            ]
        }
        if voice_id:
            payload["video_inputs"][0]["voice"]["voice_id"] = voice_id
        if session_id:
            payload["title"] = f"interview_session_{session_id}"

        response = _post_json(
            url=f"{base_url}/v2/video/generate",
            payload=payload,
            headers={
                "X-Api-Key": api_key,
                "Content-Type": "application/json",
            },
        )

        data = response.get("data", {}) if isinstance(response, dict) else {}
        request_id = str(data.get("video_id", "")).strip() or str(response.get("video_id", "")).strip() or None
        status_url = (
            str(data.get("status_url", "")).strip()
            or str(response.get("status_url", "")).strip()
            or (f"{base_url}/v1/video_status.get?video_id={request_id}" if request_id else None)
        )
        video_url = str(data.get("video_url", "")).strip() or str(response.get("video_url", "")).strip() or None

        return {
            "mode": "provider",
            "provider": "heygen",
            "text": text,
            "requestId": request_id,
            "videoUrl": video_url,
            "audioUrl": None,
            "statusUrl": status_url,
            "emotion": None,
            "speakingStyle": None,
            "visemeTimeline": [],
            "warnings": [] if video_url else ["HeyGen accepted request. Poll statusUrl until the video is ready."],
            "fallbackReason": None,
        }

    def _get_did_status(self, request_id: str) -> dict:
        api_key = os.getenv("IIA_AVATAR_API_KEY", "").strip()
        base_url = os.getenv("IIA_AVATAR_BASE_URL", "https://api.d-id.com").strip().rstrip("/")
        response = _get_json(
            url=f"{base_url}/talks/{request_id}",
            headers={
                "Authorization": f"Basic {api_key}" if not api_key.lower().startswith("basic ") else api_key,
            },
        )
        status = str(response.get("status", "unknown")).lower()
        video_url = str(response.get("result_url", "")).strip() or str(response.get("video_url", "")).strip() or None
        return {
            "provider": "did",
            "requestId": request_id,
            "status": status,
            "isReady": bool(video_url) or status in {"done", "completed"},
            "videoUrl": video_url,
            "audioUrl": None,
            "emotion": None,
            "speakingStyle": None,
            "visemeTimeline": [],
            "error": str(response.get("error", "")).strip() or None,
        }

    def _get_heygen_status(self, request_id: str) -> dict:
        api_key = os.getenv("IIA_AVATAR_API_KEY", "").strip()
        base_url = os.getenv("IIA_AVATAR_BASE_URL", "https://api.heygen.com").strip().rstrip("/")
        response = _get_json(
            url=f"{base_url}/v1/video_status.get?video_id={request_id}",
            headers={
                "X-Api-Key": api_key,
            },
        )
        data = response.get("data", {}) if isinstance(response, dict) else {}
        status = str(data.get("status", response.get("status", "unknown"))).lower()
        video_url = str(data.get("video_url", "")).strip() or str(response.get("video_url", "")).strip() or None
        return {
            "provider": "heygen",
            "requestId": request_id,
            "status": status,
            "isReady": bool(video_url) or status in {"completed", "done"},
            "videoUrl": video_url,
            "audioUrl": None,
            "emotion": None,
            "speakingStyle": None,
            "visemeTimeline": [],
            "error": str(data.get("error", response.get("error", ""))).strip() or None,
        }


def _post_json(url: str, payload: dict, headers: dict[str, str]) -> dict:
    req = urllib.request.Request(
        url=url,
        data=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:  # pragma: no cover - depends on remote provider
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - depends on network
        raise RuntimeError(f"Network error: {exc.reason}") from exc


def _get_json(url: str, headers: dict[str, str]) -> dict:
    req = urllib.request.Request(
        url=url,
        headers=headers,
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:  # pragma: no cover - depends on remote provider
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - depends on network
        raise RuntimeError(f"Network error: {exc.reason}") from exc


avatar_provider_service = AvatarProviderService()
