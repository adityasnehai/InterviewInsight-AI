import asyncio
import logging
import os
import random

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    WorkerType,
    cli,
)
from livekit.plugins import openai, simli
from aiohttp.client_exceptions import ClientResponseError

logger = logging.getLogger("simli-avatar-worker")
logger.setLevel(logging.INFO)

load_dotenv(override=True)


async def _start_simli_avatar_with_retry(
    avatar_session: simli.AvatarSession,
    *,
    session: AgentSession,
    room,
) -> None:
    max_retries = max(1, int(os.getenv("SIMLI_START_MAX_RETRIES", "5")))
    base_delay = max(1.0, float(os.getenv("SIMLI_START_RETRY_BASE_SECONDS", "3")))
    max_delay = max(base_delay, float(os.getenv("SIMLI_START_RETRY_MAX_SECONDS", "60")))
    retryable_statuses = {429, 500, 502, 503, 504}

    attempt = 0
    while True:
        attempt += 1
        try:
            await avatar_session.start(session, room=room)
            if attempt > 1:
                logger.info("Simli avatar started after retry", extra={"attempt": attempt})
            return
        except ClientResponseError as exc:
            status_code = int(getattr(exc, "status", 0) or 0)
            if status_code not in retryable_statuses or attempt >= max_retries:
                raise

            retry_after_seconds = 0.0
            try:
                retry_after_header = (exc.headers or {}).get("Retry-After")  # type: ignore[union-attr]
                if retry_after_header:
                    retry_after_seconds = max(0.0, float(retry_after_header))
            except Exception:
                retry_after_seconds = 0.0

            exponential = min(max_delay, base_delay * (2 ** (attempt - 1)))
            wait_seconds = max(retry_after_seconds, exponential) + random.uniform(0.0, 0.5)
            logger.warning(
                "Simli avatar start rate-limited/retryable failure; retrying",
                extra={
                    "attempt": attempt,
                    "max_retries": max_retries,
                    "status": status_code,
                    "wait_seconds": round(wait_seconds, 2),
                },
            )
            await asyncio.sleep(wait_seconds)


async def entrypoint(ctx: JobContext) -> None:
    session = AgentSession(
        llm=openai.realtime.RealtimeModel(voice=os.getenv("IIA_VIRTUAL_AVATAR_VOICE", "alloy")),
    )

    simli_api_key = os.getenv("SIMLI_API_KEY", "").strip() or os.getenv("IIA_AVATAR_API_KEY", "").strip()
    simli_face_id = os.getenv("SIMLI_FACE_ID", "").strip() or os.getenv("IIA_SIMLI_FACE_ID", "").strip()
    if not simli_api_key or not simli_face_id:
        raise RuntimeError("SIMLI_API_KEY (or IIA_AVATAR_API_KEY) and SIMLI_FACE_ID are required.")

    simli_avatar = simli.AvatarSession(
        simli_config=simli.SimliConfig(
            api_key=simli_api_key,
            face_id=simli_face_id,
        ),
    )
    await _start_simli_avatar_with_retry(
        simli_avatar,
        session=session,
        room=ctx.room,
    )

    await session.start(
        agent=Agent(instructions="You are a professional interviewer. Ask concise interview questions."),
        room=ctx.room,
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, worker_type=WorkerType.ROOM))
