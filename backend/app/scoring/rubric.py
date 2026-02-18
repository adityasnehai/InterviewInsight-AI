from dataclasses import dataclass


@dataclass(frozen=True)
class RubricLevel:
    min_score: float
    label: str
    descriptor: str


RUBRIC_DIMENSIONS: dict[str, dict] = {
    "communication": {
        "title": "Communication",
        "description": "Clarity of verbal delivery and structured articulation of ideas.",
        "levels": [
            RubricLevel(
                min_score=85.0,
                label="Excellent",
                descriptor="Communicates ideas with clear structure, concise language, and strong audience alignment.",
            ),
            RubricLevel(
                min_score=70.0,
                label="Good",
                descriptor="Communicates clearly with minor pacing or structure gaps that do not block understanding.",
            ),
            RubricLevel(
                min_score=0.0,
                label="Needs Improvement",
                descriptor="Communication is inconsistent; pacing, clarity, or structure frequently reduce impact.",
            ),
        ],
    },
    "technical_clarity": {
        "title": "Technical Clarity",
        "description": "Accuracy and depth when explaining technical decisions, tradeoffs, and outcomes.",
        "levels": [
            RubricLevel(
                min_score=85.0,
                label="Excellent",
                descriptor="Explains technical concepts accurately with strong depth, tradeoffs, and measurable outcomes.",
            ),
            RubricLevel(
                min_score=70.0,
                label="Good",
                descriptor="Technical explanations are mostly correct with moderate depth and occasional missing details.",
            ),
            RubricLevel(
                min_score=0.0,
                label="Needs Improvement",
                descriptor="Technical explanations are shallow or ambiguous; key reasoning and validation are missing.",
            ),
        ],
    },
    "behavioral_response": {
        "title": "Behavioral Response",
        "description": "Quality of examples, reflection, and behavioral framing under interview prompts.",
        "levels": [
            RubricLevel(
                min_score=85.0,
                label="Excellent",
                descriptor="Behavioral examples are specific, reflective, and outcome-focused with clear ownership.",
            ),
            RubricLevel(
                min_score=70.0,
                label="Good",
                descriptor="Behavioral responses are relevant and understandable but can improve in specificity or impact.",
            ),
            RubricLevel(
                min_score=0.0,
                label="Needs Improvement",
                descriptor="Behavioral responses are generic, lack clear structure, or miss tangible outcomes.",
            ),
        ],
    },
    "engagement": {
        "title": "Engagement",
        "description": "Visible attentiveness and interview presence through gaze, posture, and interaction stability.",
        "levels": [
            RubricLevel(
                min_score=85.0,
                label="Excellent",
                descriptor="Maintains strong engagement throughout with stable eye contact and controlled non-verbal cues.",
            ),
            RubricLevel(
                min_score=70.0,
                label="Good",
                descriptor="Shows consistent engagement with minor non-verbal variability.",
            ),
            RubricLevel(
                min_score=0.0,
                label="Needs Improvement",
                descriptor="Engagement fluctuates; off-screen gaze or unstable non-verbal cues reduce interviewer connection.",
            ),
        ],
    },
}


def score_to_level(score: float, levels: list[RubricLevel]) -> RubricLevel:
    value = max(0.0, min(100.0, float(score)))
    for level in levels:
        if value >= level.min_score:
            return level
    return levels[-1]


def map_scores_to_rubric(
    summary_scores: dict,
    advanced_scores: dict | None = None,
) -> dict[str, dict]:
    advanced_scores = advanced_scores or {}

    communication_score = _resolve_dimension_score(
        primary=summary_scores.get("communicationEffectiveness"),
        fallback=advanced_scores.get("communicationClarity"),
        default=summary_scores.get("speechFluency", 0.0),
    )
    technical_clarity_score = _resolve_dimension_score(
        primary=advanced_scores.get("interviewComprehension"),
        fallback=summary_scores.get("contentRelevanceScore"),
        default=summary_scores.get("speechFluency", 0.0),
    )
    behavioral_response_score = _resolve_dimension_score(
        primary=summary_scores.get("overallPerformanceScore"),
        fallback=advanced_scores.get("overallPerformance"),
        default=summary_scores.get("emotionalStability", 0.0),
    )
    engagement_score = _resolve_dimension_score(
        primary=summary_scores.get("engagementScore"),
        fallback=advanced_scores.get("engagement"),
        default=50.0,
    )

    dimension_scores = {
        "communication": communication_score,
        "technical_clarity": technical_clarity_score,
        "behavioral_response": behavioral_response_score,
        "engagement": engagement_score,
    }

    evaluation: dict[str, dict] = {}
    for dimension, score in dimension_scores.items():
        definition = RUBRIC_DIMENSIONS[dimension]
        level = score_to_level(score=score, levels=definition["levels"])
        evaluation[dimension] = {
            "title": definition["title"],
            "description": definition["description"],
            "score": round(float(score), 2),
            "level": level.label,
            "descriptor": level.descriptor,
        }
    return evaluation


def _resolve_dimension_score(primary: float | None, fallback: float | None, default: float) -> float:
    for value in (primary, fallback, default):
        if value is None:
            continue
        try:
            return max(0.0, min(100.0, float(value)))
        except Exception:
            continue
    return 0.0
