import json
import os
from typing import Any


REFLECTIVE_SYSTEM_PROMPT = (
    "You are a reflective interview coach. Respond with practical, supportive, specific improvement steps."
)

REFLECTIVE_USER_PROMPT_TEMPLATE = """
You are coaching a candidate after interview session {session_id}.

Candidate reflection:
{reflection_text}

Session summary scores:
{summary_scores_json}

System feedback messages:
{feedback_messages_json}

Provide JSON with keys:
- focusAreas: array of 3 short actionable priorities
- coachingResponse: conversational coaching paragraph (4-6 sentences)
- nextSessionPlan: array of 3 practice actions for the next interview
""".strip()


def build_reflective_prompt(
    session_id: str,
    reflection_text: str,
    summary_scores: dict,
    feedback_messages: list[str],
) -> str:
    return REFLECTIVE_USER_PROMPT_TEMPLATE.format(
        session_id=session_id,
        reflection_text=reflection_text.strip() or "No reflection text provided.",
        summary_scores_json=json.dumps(summary_scores or {}, indent=2),
        feedback_messages_json=json.dumps(feedback_messages or [], indent=2),
    )


def generate_reflective_coaching(
    session_id: str,
    reflection_text: str,
    summary_scores: dict,
    feedback_messages: list[str],
    llm_model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    prompt = build_reflective_prompt(
        session_id=session_id,
        reflection_text=reflection_text,
        summary_scores=summary_scores,
        feedback_messages=feedback_messages,
    )
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        llm_result = _generate_with_openai(prompt=prompt, api_key=api_key, model=llm_model)
        if llm_result is not None:
            llm_result["provider"] = "openai"
            llm_result["prompt"] = prompt
            return llm_result

    heuristic = _generate_with_heuristics(
        reflection_text=reflection_text,
        summary_scores=summary_scores,
        feedback_messages=feedback_messages,
    )
    heuristic["provider"] = "heuristic_fallback"
    heuristic["prompt"] = prompt
    return heuristic


def _generate_with_openai(prompt: str, api_key: str, model: str) -> dict[str, Any] | None:
    try:
        from openai import OpenAI
    except Exception:  # pragma: no cover - optional dependency
        return None

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": REFLECTIVE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = response.choices[0].message.content or "{}"
        payload = json.loads(content)
        return {
            "focusAreas": [str(item) for item in payload.get("focusAreas", [])][:3],
            "coachingResponse": str(payload.get("coachingResponse", "")).strip(),
            "nextSessionPlan": [str(item) for item in payload.get("nextSessionPlan", [])][:3],
        }
    except Exception:  # pragma: no cover - external API protection
        return None


def _generate_with_heuristics(reflection_text: str, summary_scores: dict, feedback_messages: list[str]) -> dict:
    communication = float(summary_scores.get("communicationEffectiveness", 50.0))
    engagement = float(summary_scores.get("engagementScore", 50.0))
    relevance = float(summary_scores.get("contentRelevanceScore", 50.0))

    focus_areas = []
    if communication < 70:
        focus_areas.append("Tighten answer structure using Situation-Action-Result framing.")
    if engagement < 70:
        focus_areas.append("Improve on-camera presence with consistent eye contact and steady pacing.")
    if relevance < 70:
        focus_areas.append("Anchor each answer to role-specific outcomes and technical impact.")
    if not focus_areas:
        focus_areas = [
            "Increase depth with one quantified example per answer.",
            "Practice concise opening statements for each question.",
            "Maintain consistent delivery across all segments.",
        ]

    first_feedback = feedback_messages[0] if feedback_messages else "Keep iterating on high-impact examples."
    response = (
        "Your reflection shows strong self-awareness, which is a major advantage for rapid improvement. "
        f"Current analytics suggest focusing first on: {focus_areas[0]} "
        f"Also pay attention to this signal from the system: {first_feedback} "
        "In the next mock interview, prioritize clarity first, then add technical depth with concise evidence. "
        "Track one measurable target for each practice run so progress becomes visible over time."
    )
    return {
        "focusAreas": focus_areas[:3],
        "coachingResponse": response,
        "nextSessionPlan": [
            "Rehearse 3 answers using concise STAR structure with metrics.",
            "Record a 10-minute mock and review pacing + eye contact.",
            "Rewrite one weak answer to highlight tradeoffs and outcomes.",
        ],
    }
