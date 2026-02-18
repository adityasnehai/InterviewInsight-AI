from datetime import datetime, timezone

from app.models.reports import InterviewReportRequest


def build_interview_report_payload(
    session_id: str,
    session_data: dict,
    analysis_result: dict,
    scoring_result: dict | None,
    request_payload: InterviewReportRequest,
) -> dict:
    session_meta = analysis_result.get("sessionMeta", {})
    summary_scores = _to_float_dict(analysis_result.get("summaryScores", {}))

    if scoring_result and scoring_result.get("summaryScores"):
        summary_scores = _to_float_dict(scoring_result.get("summaryScores", {}))

    detailed_scores = (
        scoring_result.get("detailedScores", {})
        if scoring_result and scoring_result.get("detailedScores")
        else analysis_result.get("detailedScores", {})
    )

    strengths = []
    improvements = []
    feedback_summary = analysis_result.get("feedbackSummary", {})
    if feedback_summary:
        strengths = list(feedback_summary.get("strengths", []))
        improvements = list(feedback_summary.get("improvements", []))

    feedback_messages = []
    if scoring_result and scoring_result.get("feedbackMessages"):
        feedback_messages = list(scoring_result.get("feedbackMessages", []))
    else:
        feedback_messages = list(analysis_result.get("feedbackMessages", []))

    segment_summaries = []
    for segment in analysis_result.get("segmentLabels", []):
        segment_summaries.append(
            {
                "segmentId": str(segment.get("segmentId", "")),
                "label": str(segment.get("label", "")),
                "startTime": float(segment.get("startTime", 0.0)),
                "endTime": float(segment.get("endTime", 0.0)),
                "scores": {
                    "engagement": float(segment.get("engagementScore", 0.0)),
                    "speechFluency": float(segment.get("speechFluency", 0.0)),
                    "textRelevance": float(segment.get("textRelevanceScore", 0.0)),
                },
                "dominantEmotion": str(segment.get("dominantEmotion", "neutral")),
            }
        )

    chart_snapshots = None
    if request_payload.includeChartSnapshots:
        chart_snapshots = {
            key: value
            for key, value in (request_payload.chartSnapshots or {}).items()
            if isinstance(value, str) and value.startswith("data:image/")
        }

    generated_at = datetime.now(timezone.utc)
    report_title = "InterviewInsight AI Report"
    user_name = request_payload.userName or session_data.get("userId")

    return {
        "title": report_title,
        "generatedAt": generated_at,
        "sessionMetadata": {
            "sessionId": session_id,
            "userName": user_name,
            "jobRole": session_meta.get("jobRole") or session_data.get("jobRole"),
            "domain": session_meta.get("domain") or session_data.get("domain"),
            "interviewDateTime": session_meta.get("dateTime") or session_data.get("startedAt"),
            "reportGeneratedAt": generated_at,
            "requestedFormat": request_payload.format,
        },
        "overallScores": summary_scores,
        "detailedScores": detailed_scores,
        "segmentSummaries": segment_summaries,
        "feedbackMessages": feedback_messages,
        "strengths": strengths,
        "improvements": improvements,
        "chartSnapshots": chart_snapshots,
    }


def _to_float_dict(data: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in data.items():
        try:
            out[str(key)] = float(value)
        except Exception:
            continue
    return out
