import json
import os
import re
import statistics
from typing import Any

SYSTEM_PROMPT = (
    "You are an interview evaluator. Score content quality objectively and return compact JSON only."
)

USER_PROMPT_TEMPLATE = """
Evaluate the interview transcript for a {job_role} role in {domain}.

Scoring criteria (0-100):
1) answer_depth: how specific and evidence-based the responses are.
2) technical_correctness: how technically accurate and sound the responses are.
3) job_role_relevance: how relevant the answers are to the target role.

Return strict JSON with keys:
answerDepth, technicalCorrectness, jobRoleRelevance, overallLLMJudgeScore, rationale.

Transcript:
{transcript}
""".strip()


def build_llm_judge_prompt(transcript_text: str, job_role: str, domain: str) -> str:
    transcript = transcript_text.strip() or "No transcript provided."
    return USER_PROMPT_TEMPLATE.format(
        transcript=transcript,
        job_role=job_role or "generalist",
        domain=domain or "general domain",
    )


def evaluate_llm_judge(
    transcript_text: str,
    job_role: str,
    domain: str,
    llm_model: str = "gpt-4o-mini",
    allow_remote: bool = True,
) -> dict[str, Any]:
    prompt = build_llm_judge_prompt(
        transcript_text=transcript_text,
        job_role=job_role,
        domain=domain,
    )
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and allow_remote:
        llm_result = _evaluate_with_openai(prompt=prompt, model=llm_model, api_key=api_key)
        if llm_result is not None:
            llm_result["prompt"] = prompt
            llm_result["provider"] = "openai"
            return llm_result

    heuristic_result = _evaluate_with_heuristics(
        transcript_text=transcript_text,
        job_role=job_role,
        domain=domain,
    )
    heuristic_result["prompt"] = prompt
    heuristic_result["provider"] = "heuristic_fallback"
    return heuristic_result


def _evaluate_with_openai(prompt: str, model: str, api_key: str) -> dict[str, Any] | None:
    try:
        from openai import OpenAI
    except Exception:  # pragma: no cover - optional dependency
        return None

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content or "{}"
        data = json.loads(text)
        return {
            "answerDepth": _clamp(float(data.get("answerDepth", 0.0)), 0.0, 100.0),
            "technicalCorrectness": _clamp(float(data.get("technicalCorrectness", 0.0)), 0.0, 100.0),
            "jobRoleRelevance": _clamp(float(data.get("jobRoleRelevance", 0.0)), 0.0, 100.0),
            "overallLLMJudgeScore": _clamp(float(data.get("overallLLMJudgeScore", 0.0)), 0.0, 100.0),
            "rationale": str(data.get("rationale", "")).strip() or "No rationale provided by LLM.",
        }
    except Exception:  # pragma: no cover - external API protection
        return None


def _evaluate_with_heuristics(transcript_text: str, job_role: str, domain: str) -> dict[str, Any]:
    normalized = transcript_text.lower().strip()
    words = re.findall(r"\b[\w'-]+\b", normalized)
    word_count = len(words)
    sentence_count = max(1, len(re.findall(r"[.!?]", transcript_text)))
    avg_sentence_length = word_count / sentence_count
    lexical_diversity = len(set(words)) / word_count if word_count else 0.0

    depth_score = _clamp((min(word_count, 500) / 500.0) * 55.0 + lexical_diversity * 45.0, 0.0, 100.0)

    technical_keywords = _collect_keywords(job_role, domain)
    keyword_hits = sum(1 for token in words if token in technical_keywords)
    keyword_score = _clamp((keyword_hits / max(8, len(technical_keywords))) * 100.0, 0.0, 100.0)
    structure_score = _clamp((avg_sentence_length / 20.0) * 100.0, 0.0, 100.0)
    correctness_score = _clamp((keyword_score * 0.7) + (structure_score * 0.3), 0.0, 100.0)

    relevance_terms = [token for token in technical_keywords if token in normalized]
    relevance_score = _clamp((len(relevance_terms) / max(5, len(technical_keywords) // 2)) * 100.0, 0.0, 100.0)

    overall = _clamp(statistics.mean([depth_score, correctness_score, relevance_score]), 0.0, 100.0)
    rationale = (
        "Heuristic LLM-judge fallback used because external LLM access is unavailable. "
        f"Depth relied on transcript length/diversity ({word_count} words, {lexical_diversity:.2f} lexical diversity), "
        f"technical correctness used keyword and structure signals ({keyword_hits} keyword hits), and "
        f"relevance measured overlap with role/domain terms ({len(relevance_terms)} matches)."
    )
    return {
        "answerDepth": round(depth_score, 2),
        "technicalCorrectness": round(correctness_score, 2),
        "jobRoleRelevance": round(relevance_score, 2),
        "overallLLMJudgeScore": round(overall, 2),
        "rationale": rationale,
    }


def _collect_keywords(job_role: str, domain: str) -> set[str]:
    base = {
        "architecture",
        "design",
        "scalable",
        "performance",
        "testing",
        "debugging",
        "system",
        "data",
        "analysis",
        "metrics",
        "api",
        "security",
        "reliability",
        "deployment",
    }
    role_tokens = set(re.findall(r"[a-z]+", (job_role or "").lower()))
    domain_tokens = set(re.findall(r"[a-z]+", (domain or "").lower()))
    return {token for token in base | role_tokens | domain_tokens if len(token) > 2}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))
