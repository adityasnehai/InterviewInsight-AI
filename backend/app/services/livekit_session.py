import os
from uuid import uuid4


def create_simli_livekit_session(*, session_id: str, user_id: str) -> dict:
    ws_url = os.getenv("LIVEKIT_URL", "").strip()
    api_key = os.getenv("LIVEKIT_API_KEY", "").strip()
    api_secret = os.getenv("LIVEKIT_API_SECRET", "").strip()
    face_id = (
        os.getenv("SIMLI_FACE_ID", "").strip()
        or os.getenv("IIA_SIMLI_FACE_ID", "").strip()
    )

    if not ws_url:
        raise ValueError("LIVEKIT_URL is required for Simli LiveKit mode.")
    if not api_key:
        raise ValueError("LIVEKIT_API_KEY is required for Simli LiveKit mode.")
    if not api_secret:
        raise ValueError("LIVEKIT_API_SECRET is required for Simli LiveKit mode.")
    if not face_id:
        raise ValueError("SIMLI_FACE_ID (or IIA_SIMLI_FACE_ID) is required for Simli LiveKit mode.")

    try:
        from livekit import api  # type: ignore
    except Exception as exc:
        raise RuntimeError("livekit-api dependency is not installed.") from exc

    room_name = f"iia-{session_id}"
    participant_identity = f"{user_id}-{uuid4().hex[:8]}"

    participant_token = (
        api.AccessToken(api_key, api_secret)
        .with_identity(participant_identity)
        .with_name(user_id)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            )
        )
        .to_jwt()
    )

    return {
        "provider": "simli",
        "roomName": room_name,
        "participantIdentity": participant_identity,
        "participantToken": participant_token,
        "wsUrl": ws_url,
        "faceId": face_id,
    }
