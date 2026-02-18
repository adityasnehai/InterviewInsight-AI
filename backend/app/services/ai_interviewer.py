import json
import os
import re
from datetime import datetime
from typing import Any

INTERVIEW_STRATEGY_STAGES = [
    {
        "name": "greeting_and_context",
        "goal": "Start friendly, set context, and collect a concise introduction.",
        "template": "Great to meet you. Could you briefly introduce yourself and your background for this {job_role} role?",
    },
    {
        "name": "motivation_and_fit",
        "goal": "Assess motivation for the role and domain alignment.",
        "template": "What specifically interests you about this {job_role} role in {domain}, and where do you think you can add the most value?",
    },
    {
        "name": "technical_depth",
        "goal": "Probe technical decision-making, tradeoffs, and measurable outcomes.",
        "template": "Walk me through a recent technical decision related to {domain}. What options did you evaluate and why?",
    },
    {
        "name": "collaboration_and_behavior",
        "goal": "Understand communication style and conflict resolution.",
        "template": "Tell me about a disagreement with a teammate or stakeholder and how you handled it.",
    },
    {
        "name": "reflection_and_plan",
        "goal": "Close with reflection and forward-looking thinking.",
        "template": "If you joined as a {job_role}, what would your 30-60-90 day plan be?",
    },
]

SYSTEM_PROMPT = (
    "You are an expert technical interviewer. Ask one concise, job-relevant question."
    " Follow the stage strategy in the prompt."
    " Do not repeat prior interviewer questions."
    " Keep the question specific, evaluative, and conversational."
)

USER_PROMPT_TEMPLATE = """
You are interviewing a candidate for role: {job_role} in domain: {domain}.
Current stage:
- name: {stage_name}
- goal: {stage_goal}

Existing transcript turns:
{turns_json}

Generate one next interview question only as JSON:
{{"question":"..."}}
Keep the question to 1-2 sentences, natural and conversational.
""".strip()

CLARIFICATION_PROMPT_TEMPLATE = """
You are interviewing a candidate for role: {job_role} in domain: {domain}.

Current question:
{current_question}

Candidate answer:
{candidate_answer}

Ask one short clarification follow-up that requests concrete detail or an example.
Return JSON only:
{{"question":"..."}}
""".strip()

LOW_SIGNAL_PHRASES = {
    "i do not know",
    "not sure",
    "no idea",
    "can't say",
    "cannot say",
    "nothing much",
    "na",
    "n/a",
}
MAX_CONTEXT_TURNS = 10
MAX_TURN_TEXT_LENGTH = 280

def generate_followup_question(
    job_role: str,
    domain: str,
    turns: list[dict[str, Any]],
    current_question_index: int | None = None,
) -> str:
    stage = _resolve_stage(turns=turns, current_question_index=current_question_index)
    safe_turns = _prepare_turns_for_prompt(turns)
    prompt = USER_PROMPT_TEMPLATE.format(
        job_role=(job_role or "generalist role").strip(),
        domain=(domain or "general domain").strip(),
        stage_name=stage["name"],
        stage_goal=stage["goal"],
        turns_json=json.dumps(safe_turns, ensure_ascii=True),
    )
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        candidate = _generate_with_openai(prompt=prompt, api_key=api_key)
        if candidate and _passes_question_guardrails(candidate=candidate, turns=safe_turns):
            return candidate
    return _fallback_followup(
        job_role=job_role,
        domain=domain,
        turns=safe_turns,
        current_question_index=current_question_index,
    )


def generate_clarification_question(
    *,
    job_role: str,
    domain: str,
    current_question: str,
    candidate_answer: str,
    turns: list[dict[str, Any]],
) -> str:
    safe_current_question = str(current_question or "").strip()
    safe_answer = str(candidate_answer or "").strip()
    safe_turns = _prepare_turns_for_prompt(turns)
    fallback = _fallback_clarification(
        current_question=safe_current_question,
        candidate_answer=safe_answer,
    )
    if not safe_current_question:
        return fallback

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return fallback

    prompt = CLARIFICATION_PROMPT_TEMPLATE.format(
        job_role=(job_role or "generalist role").strip(),
        domain=(domain or "general domain").strip(),
        current_question=safe_current_question,
        candidate_answer=safe_answer,
    )
    candidate = _generate_with_openai(prompt=prompt, api_key=api_key)
    if candidate and _passes_question_guardrails(candidate=candidate, turns=safe_turns):
        return candidate
    return fallback


def evaluate_answer_quality(answer_text: str, current_question: str) -> dict[str, Any]:
    answer = _normalize_for_overlap(answer_text)
    question = _normalize_for_overlap(current_question)
    words = [token for token in answer.split(" ") if token]
    word_count = len(words)
    overlap = _token_overlap_ratio(answer, question) if question else 0.0

    has_signal = any(
        marker in answer
        for marker in (
            "because",
            "for example",
            "for instance",
            "tradeoff",
            "result",
            "impact",
            "improved",
            "reduced",
            "increased",
            "measured",
            "learned",
            "challenge",
        )
    )
    low_signal = any(phrase in answer for phrase in LOW_SIGNAL_PHRASES)

    score = 0.0
    score += min(word_count / 24.0, 1.0) * 0.55
    score += min(overlap, 1.0) * 0.2
    score += 0.25 if has_signal else 0.0
    if low_signal:
        score *= 0.4
    score = max(0.0, min(score, 1.0))

    needs_clarification = score < 0.42 or word_count < 8 or low_signal
    reason = "answer_was_concise"
    if low_signal:
        reason = "answer_lacked_substance"
    elif word_count < 8:
        reason = "answer_too_short"
    elif score < 0.42:
        reason = "answer_needs_specifics"

    return {
        "score": score,
        "needsClarification": bool(needs_clarification),
        "wordCount": word_count,
        "reason": reason,
    }


def _generate_with_openai(prompt: str, api_key: str) -> str | None:
    try:
        from openai import OpenAI
    except Exception:  # pragma: no cover - optional dependency
        return None

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        raw = response.choices[0].message.content or "{}"
        payload = json.loads(raw)
        question = str(payload.get("question", "")).strip()
        if not question:
            return None
        return _normalize_question_text(question)
    except Exception:  # pragma: no cover - external failures
        return None


def _fallback_followup(
    job_role: str,
    domain: str,
    turns: list[dict[str, Any]],
    current_question_index: int | None = None,
) -> str:
    stage = _resolve_stage(turns=turns, current_question_index=current_question_index)
    fallback = stage["template"].format(
        job_role=(job_role or "this role").strip(),
        domain=(domain or "this domain").strip(),
    )
    return _normalize_question_text(fallback)


def _fallback_clarification(current_question: str, candidate_answer: str) -> str:
    if candidate_answer and len(candidate_answer.split()) < 8:
        return "Thanks. Could you add a concrete example with what you did and the outcome?"
    if current_question:
        return "Could you go one level deeper on that, including your reasoning and measurable impact?"
    return "Could you share a specific example and outcome for that?"


def _resolve_stage(turns: list[dict[str, Any]], current_question_index: int | None = None) -> dict[str, str]:
    if isinstance(current_question_index, int) and current_question_index >= 0:
        idx = current_question_index
    else:
        user_turns = [turn for turn in turns if str(turn.get("role")) == "user"]
        idx = len(user_turns)
    bounded_idx = min(max(idx, 0), len(INTERVIEW_STRATEGY_STAGES) - 1)
    return INTERVIEW_STRATEGY_STAGES[bounded_idx]


def _to_json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _to_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(item) for item in value]
    return value


def _prepare_turns_for_prompt(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    recent_turns = turns[-MAX_CONTEXT_TURNS:]
    for turn in recent_turns:
        role = str(turn.get("role", "")).strip().lower()
        if role not in {"assistant", "user"}:
            continue
        text = str(turn.get("text", "")).strip()
        if not text:
            continue
        text = re.sub(r"\s+", " ", text)[:MAX_TURN_TEXT_LENGTH]
        normalized = _normalize_for_overlap(text)
        if cleaned:
            previous = cleaned[-1]
            if previous["role"] == role and _normalize_for_overlap(str(previous["text"])) == normalized:
                continue
        cleaned.append({"role": role, "text": text})
    return _to_json_safe(cleaned)


def _passes_question_guardrails(candidate: str, turns: list[dict[str, Any]]) -> bool:
    question = _normalize_question_text(candidate)
    if len(question) < 12 or len(question) > 260:
        return False
    forbidden = (
        "as an ai",
        "language model",
        "i cannot",
        "policy",
    )
    lowered = question.lower()
    if any(token in lowered for token in forbidden):
        return False

    recent_assistant_questions = [
        str(turn.get("text", "")).strip()
        for turn in turns[-6:]
        if str(turn.get("role", "")).lower() == "assistant"
    ]
    for existing in recent_assistant_questions:
        overlap = _token_overlap_ratio(_normalize_for_overlap(question), _normalize_for_overlap(existing))
        if overlap >= 0.86:
            return False
    return True


def _normalize_question_text(text: str) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if not compact:
        return ""
    if compact[-1] not in {"?", ".", "!"}:
        compact = f"{compact}?"
    return compact


def _normalize_for_overlap(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", str(text or "").lower())).strip()


def _token_overlap_ratio(candidate_text: str, reference_text: str) -> float:
    candidate_tokens = set(candidate_text.split(" "))
    reference_tokens = set(reference_text.split(" "))
    candidate_tokens.discard("")
    reference_tokens.discard("")
    if not candidate_tokens or not reference_tokens:
        return 0.0
    overlap = len(candidate_tokens.intersection(reference_tokens))
    return overlap / len(candidate_tokens)
