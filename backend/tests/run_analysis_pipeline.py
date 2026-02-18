import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.analysis import run_video_analysis
from app.models.analysis import VideoAnalysisRequest
from app.models.session import SessionStartRequest
from app.services.session_store import session_store

try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover - optional dependencies
    cv2 = None
    np = None


def _generate_sample_video(duration_seconds: int = 3, fps: int = 10) -> Path:
    if cv2 is None or np is None:
        raise RuntimeError("OpenCV + NumPy are required to auto-generate a sample video")

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    output_path = Path(tmp.name)

    width, height = 640, 360
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )

    for frame_idx in range(duration_seconds * fps):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.putText(
            frame,
            f"Interview sample frame {frame_idx}",
            (20, 180),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )
        writer.write(frame)
    writer.release()
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run InterviewInsight multimodal analysis pipeline.")
    parser.add_argument("--video", dest="video_path", default=None, help="Path to sample interview video (.mp4/.webm)")
    parser.add_argument(
        "--lightweight",
        action="store_true",
        help="Disable heavyweight model downloads and run deterministic fallback logic.",
    )
    args = parser.parse_args()

    if args.lightweight:
        os.environ["IIA_DISABLE_MODEL_LOADING"] = "1"

    if args.video_path:
        video_path = Path(args.video_path).expanduser()
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")
    else:
        video_path = _generate_sample_video()

    session = session_store.create_session(
        SessionStartRequest(userId="local-test-user", jobRole="Software Engineer", domain="AI")
    )
    payload = VideoAnalysisRequest(
        sessionId=session["sessionId"],
        videoFilePath=str(video_path),
        frameFps=3,
        windowSizeSeconds=2.0,
    )

    result = run_video_analysis(payload)

    print("Session ID:", result.sessionId)
    print("Transcript:", result.transcriptText[:120])
    print("Overall engagement:", round(result.engagementMetrics.overallEngagement, 3))
    print("Fused segments:", len(result.fusedFeatureVectors))
    print("Results available via GET /analysis/{sessionId}/results")


if __name__ == "__main__":
    main()
