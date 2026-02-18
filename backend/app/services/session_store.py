from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.db import SessionLocal
from app.db_models import AnalysisJobDB, RefreshTokenDB, SessionDB, UserAccountDB, UserProfileDB
from app.models.session import QuestionResponse, SessionStartRequest
from app.services.auth_service import (
    access_expires_in_seconds,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


class SessionStore:
    def create_session(self, payload: SessionStartRequest) -> dict:
        session_id = str(uuid4())
        questions = self._build_placeholder_questions(payload.jobRole, payload.domain)
        session_data = {
            "sessionId": session_id,
            "userId": payload.userId,
            "jobRole": payload.jobRole,
            "domain": payload.domain,
            "status": "started",
            "startedAt": datetime.now(timezone.utc),
            "questions": questions,
            "responses": [],
            "uploads": [],
            "reflections": [],
            "analysisResult": None,
            "scoringResult": None,
            "advancedScoringResult": None,
            "reportResult": None,
            "liveInterview": {
                "active": False,
                "complete": False,
                "questionIndex": 0,
                "currentQuestionId": None,
                "currentQuestionText": None,
                "currentQuestionAskedAt": None,
                "turns": [],
                "timelineMarkers": [],
                "clarificationCounts": {},
            },
        }
        with SessionLocal() as db:
            self._ensure_user_profile(db, payload.userId)
            row = SessionDB(
                session_id=session_id,
                user_id=payload.userId,
                job_role=payload.jobRole,
                domain=payload.domain,
                status="started",
                started_at=_to_datetime(session_data["startedAt"]),
                data_json=_jsonify(session_data),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._row_to_session_dict(row)

    def get_session(self, session_id: str) -> dict | None:
        with SessionLocal() as db:
            row = self._get_session_row(db, session_id)
            if row is None:
                return None
            return self._row_to_session_dict(row)

    def get_sessions_for_user(self, user_id: str) -> list[dict]:
        with SessionLocal() as db:
            stmt = select(SessionDB).where(SessionDB.user_id == str(user_id)).order_by(SessionDB.started_at.desc())
            rows = db.execute(stmt).scalars().all()

        sessions: list[dict] = []
        for row in rows:
            session_payload = self._row_to_session_dict(row)
            scoring_result = session_payload.get("scoringResult") or {}
            sessions.append(
                {
                    "sessionId": session_payload["sessionId"],
                    "jobRole": session_payload.get("jobRole"),
                    "domain": session_payload.get("domain"),
                    "status": session_payload.get("status"),
                    "startedAt": session_payload.get("startedAt"),
                    "analysisReady": session_payload.get("analysisResult") is not None,
                    "scoringReady": session_payload.get("scoringResult") is not None,
                    "overallPerformanceScore": float(
                        (scoring_result.get("summaryScores") or {}).get("overallPerformanceScore", 0.0)
                    ),
                    "liveComplete": bool(
                        (session_payload.get("liveInterview") or {}).get("complete", False)
                    ),
                }
            )
        return sessions

    def session_belongs_to_user(self, session_id: str, user_id: str) -> bool:
        with SessionLocal() as db:
            row = self._get_session_row(db, session_id)
            if row is None:
                return False
            return str(row.user_id) == str(user_id)

    def get_questions(self, session_id: str) -> list[dict] | None:
        session = self.get_session(session_id)
        if not session:
            return None
        return list(session.get("questions") or [])

    def add_response(self, session_id: str, payload: QuestionResponse) -> dict | None:
        with SessionLocal() as db:
            row = self._get_session_row(db, session_id)
            if row is None:
                return None
            data = self._read_data(row)
            response = {
                "questionId": payload.questionId,
                "responseText": payload.responseText,
                "submittedAt": datetime.now(timezone.utc),
            }
            responses = list(data.get("responses") or [])
            responses.append(response)
            data["responses"] = responses
            data["status"] = "in_progress"
            row.status = "in_progress"
            row.data_json = _jsonify(data)
            db.add(row)
            db.commit()
            return _jsonify(response)

    def initialize_live_interview(self, session_id: str) -> dict | None:
        with SessionLocal() as db:
            row = self._get_session_row(db, session_id)
            if row is None:
                return None
            data = self._read_data(row)
            questions = list(data.get("questions") or [])
            if not questions:
                return None
            first_question = questions[0]
            now_dt = datetime.now(timezone.utc)
            live_state = {
                "active": True,
                "complete": False,
                "questionIndex": 0,
                "currentQuestionId": first_question.get("questionId"),
                "currentQuestionText": first_question.get("questionText"),
                "currentQuestionAskedAt": now_dt,
                "turns": [
                    {
                        "role": "assistant",
                        "text": first_question.get("questionText"),
                        "questionId": first_question.get("questionId"),
                        "timestamp": now_dt,
                    }
                ],
                "timelineMarkers": [],
                "clarificationCounts": {},
            }
            data["liveInterview"] = live_state
            data["status"] = "live_started"
            row.status = "live_started"
            row.data_json = _jsonify(data)
            db.add(row)
            db.commit()
            return _jsonify(live_state)

    def get_live_state(self, session_id: str) -> dict | None:
        session = self.get_session(session_id)
        if not session:
            return None
        live_state = dict(session.get("liveInterview") or {})
        live_state.setdefault("clarificationCounts", {})
        return live_state

    def get_live_clarification_count(self, session_id: str, question_index: int) -> int:
        live_state = self.get_live_state(session_id) or {}
        counts = live_state.get("clarificationCounts") or {}
        return int(counts.get(str(int(question_index)), 0))

    def increment_live_clarification_count(self, session_id: str, question_index: int) -> int:
        with SessionLocal() as db:
            row = self._get_session_row(db, session_id)
            if row is None:
                return 0
            data = self._read_data(row)
            live_state = dict(data.get("liveInterview") or {})
            counts = dict(live_state.get("clarificationCounts") or {})
            key = str(int(question_index))
            next_count = int(counts.get(key, 0)) + 1
            counts[key] = next_count
            live_state["clarificationCounts"] = counts
            data["liveInterview"] = live_state
            row.data_json = _jsonify(data)
            db.add(row)
            db.commit()
            return next_count

    def record_live_answer(
        self,
        session_id: str,
        answer_text: str,
        *,
        question_asked_at: str | None = None,
        answer_started_at: str | None = None,
        answer_ended_at: str | None = None,
        transcript_confidence: float | None = None,
        skipped: bool = False,
    ) -> dict | None:
        with SessionLocal() as db:
            row = self._get_session_row(db, session_id)
            if row is None:
                return None
            data = self._read_data(row)
            live_state = dict(data.get("liveInterview") or {})
            if not live_state.get("active"):
                return None

            current_question_id = live_state.get("currentQuestionId")
            current_question_index = int(live_state.get("questionIndex", 0))

            asked_at_dt = (
                _to_datetime(question_asked_at)
                if question_asked_at
                else _to_datetime(live_state.get("currentQuestionAskedAt"))
            )
            answer_started_dt = _to_datetime(answer_started_at) if answer_started_at else datetime.now(timezone.utc)
            answer_ended_dt = _to_datetime(answer_ended_at) if answer_ended_at else datetime.now(timezone.utc)

            if current_question_id:
                responses = list(data.get("responses") or [])
                responses.append(
                    {
                        "questionId": current_question_id,
                        "responseText": answer_text,
                        "submittedAt": datetime.now(timezone.utc),
                        "skipped": bool(skipped),
                        "timeline": {
                            "questionAskedAt": asked_at_dt,
                            "answerStartedAt": answer_started_dt,
                            "answerEndedAt": answer_ended_dt,
                        },
                        "transcriptConfidence": transcript_confidence,
                    }
                )
                data["responses"] = responses

            turns = list(live_state.get("turns") or [])
            turns.append(
                {
                    "role": "user",
                    "text": answer_text,
                    "questionId": current_question_id,
                    "timestamp": datetime.now(timezone.utc),
                    "skipped": bool(skipped),
                }
            )
            live_state["turns"] = turns

            markers = list(live_state.get("timelineMarkers") or [])
            markers.append(
                {
                    "questionId": current_question_id,
                    "questionIndex": current_question_index,
                    "questionAskedAt": asked_at_dt,
                    "answerStartedAt": answer_started_dt,
                    "answerEndedAt": answer_ended_dt,
                    "submittedAt": datetime.now(timezone.utc),
                    "wasSkipped": bool(skipped),
                }
            )
            live_state["timelineMarkers"] = markers

            data["liveInterview"] = live_state
            data["status"] = "live_in_progress"
            row.status = "live_in_progress"
            row.data_json = _jsonify(data)
            db.add(row)
            db.commit()
            return _jsonify(live_state)

    def record_live_skip(
        self,
        session_id: str,
        *,
        question_asked_at: str | None = None,
        skipped_at: str | None = None,
    ) -> dict | None:
        skipped_timestamp = skipped_at or datetime.now(timezone.utc).isoformat()
        return self.record_live_answer(
            session_id=session_id,
            answer_text="[Question skipped by user]",
            question_asked_at=question_asked_at,
            answer_started_at=skipped_timestamp,
            answer_ended_at=skipped_timestamp,
            transcript_confidence=None,
            skipped=True,
        )

    def set_live_next_question(
        self,
        session_id: str,
        question_id: str,
        question_text: str,
        question_index: int,
    ) -> dict | None:
        with SessionLocal() as db:
            row = self._get_session_row(db, session_id)
            if row is None:
                return None
            data = self._read_data(row)
            live_state = dict(data.get("liveInterview") or {})
            live_state["active"] = True
            live_state["complete"] = False
            live_state["questionIndex"] = int(question_index)
            live_state["currentQuestionId"] = question_id
            live_state["currentQuestionText"] = question_text
            live_state["currentQuestionAskedAt"] = datetime.now(timezone.utc)
            turns = list(live_state.get("turns") or [])
            turns.append(
                {
                    "role": "assistant",
                    "text": question_text,
                    "questionId": question_id,
                    "timestamp": datetime.now(timezone.utc),
                }
            )
            live_state["turns"] = turns
            data["liveInterview"] = live_state
            data["status"] = "live_in_progress"
            row.status = "live_in_progress"
            row.data_json = _jsonify(data)
            db.add(row)
            db.commit()
            return _jsonify(live_state)

    def mark_live_complete(self, session_id: str) -> dict | None:
        with SessionLocal() as db:
            row = self._get_session_row(db, session_id)
            if row is None:
                return None
            data = self._read_data(row)
            live_state = dict(data.get("liveInterview") or {})
            live_state["active"] = False
            live_state["complete"] = True
            data["liveInterview"] = live_state
            if str(data.get("status", "")).startswith("live"):
                data["status"] = "live_completed"
                row.status = "live_completed"
            row.data_json = _jsonify(data)
            db.add(row)
            db.commit()
            return _jsonify(live_state)

    def add_upload(self, session_id: str, video_file: str, audio_file: str | None = None) -> dict | None:
        with SessionLocal() as db:
            row = self._get_session_row(db, session_id)
            if row is None:
                return None
            data = self._read_data(row)
            upload_entry = {
                "videoFile": video_file,
                "audioFile": audio_file,
                "uploadedAt": datetime.now(timezone.utc),
            }
            uploads = list(data.get("uploads") or [])
            uploads.append(upload_entry)
            data["uploads"] = uploads
            data["status"] = "media_uploaded"
            row.status = "media_uploaded"
            row.data_json = _jsonify(data)
            db.add(row)
            db.commit()
            return _jsonify(upload_entry)

    def get_status(self, session_id: str) -> dict | None:
        session = self.get_session(session_id)
        if not session:
            return None
        return {
            "sessionId": session["sessionId"],
            "userId": session["userId"],
            "jobRole": session["jobRole"],
            "domain": session["domain"],
            "status": session["status"],
            "startedAt": session["startedAt"],
            "questionsCount": len(session.get("questions") or []),
            "responsesCount": len(session.get("responses") or []),
            "analysisReady": session.get("analysisResult") is not None,
            "scoringReady": session.get("scoringResult") is not None,
            "advancedScoringReady": session.get("advancedScoringResult") is not None,
            "reportReady": session.get("reportResult") is not None,
        }

    def set_analysis_result(self, session_id: str, analysis_result: dict) -> dict | None:
        return self._set_session_result(session_id, "analysisResult", analysis_result, status_value="analysis_ready")

    def get_analysis_result(self, session_id: str) -> dict | None:
        session = self.get_session(session_id)
        if not session:
            return None
        return session.get("analysisResult")

    def set_scoring_result(self, session_id: str, scoring_result: dict) -> dict | None:
        return self._set_session_result(session_id, "scoringResult", scoring_result, status_value="scored")

    def get_scoring_result(self, session_id: str) -> dict | None:
        session = self.get_session(session_id)
        if not session:
            return None
        return session.get("scoringResult")

    def set_report_result(self, session_id: str, report_result: dict) -> dict | None:
        return self._set_session_result(session_id, "reportResult", report_result, status_value="report_ready")

    def get_report_result(self, session_id: str) -> dict | None:
        session = self.get_session(session_id)
        if not session:
            return None
        return session.get("reportResult")

    def set_advanced_scoring_result(self, session_id: str, advanced_scoring_result: dict) -> dict | None:
        with SessionLocal() as db:
            row = self._get_session_row(db, session_id)
            if row is None:
                return None
            data = self._read_data(row)
            data["advancedScoringResult"] = advanced_scoring_result
            if data.get("status") in {"analysis_ready", "scored"}:
                data["status"] = "advanced_scored"
                row.status = "advanced_scored"
            row.data_json = _jsonify(data)
            db.add(row)
            db.commit()
            return _jsonify(advanced_scoring_result)

    def get_advanced_scoring_result(self, session_id: str) -> dict | None:
        session = self.get_session(session_id)
        if not session:
            return None
        return session.get("advancedScoringResult")

    def upsert_user_profile(
        self,
        user_id: str,
        display_name: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        with SessionLocal() as db:
            profile = db.get(UserProfileDB, str(user_id))
            if profile is None:
                profile = UserProfileDB(
                    user_id=str(user_id),
                    display_name=display_name,
                    metadata_json=dict(metadata or {}),
                    created_at=datetime.now(timezone.utc),
                )
            else:
                if display_name is not None:
                    profile.display_name = display_name
                merged_metadata = dict(profile.metadata_json or {})
                if metadata:
                    merged_metadata.update(metadata)
                profile.metadata_json = merged_metadata
                profile.updated_at = datetime.now(timezone.utc)
            db.add(profile)
            db.commit()
            db.refresh(profile)
            return {
                "userId": profile.user_id,
                "displayName": profile.display_name,
                "metadata": dict(profile.metadata_json or {}),
                "createdAt": profile.created_at,
            }

    def get_user_profile(self, user_id: str) -> dict | None:
        with SessionLocal() as db:
            profile = db.get(UserProfileDB, str(user_id))
            if profile is None:
                return None
            return {
                "userId": profile.user_id,
                "displayName": profile.display_name,
                "metadata": dict(profile.metadata_json or {}),
                "createdAt": profile.created_at,
            }

    def get_user_performance_history(self, user_id: str) -> dict | None:
        profile = self.get_user_profile(user_id)
        with SessionLocal() as db:
            stmt = select(SessionDB).where(SessionDB.user_id == str(user_id))
            rows = db.execute(stmt).scalars().all()

        history: list[dict] = []
        for row in rows:
            payload = self._row_to_session_dict(row)
            scoring = payload.get("scoringResult") or {}
            summary_scores = scoring.get("summaryScores") or {}
            rubric = scoring.get("rubricEvaluation") or {}
            if not summary_scores and not rubric:
                continue
            history.append(
                {
                    "sessionId": payload["sessionId"],
                    "timestamp": _to_datetime(payload.get("startedAt")),
                    "summaryScores": {
                        str(key): float(value)
                        for key, value in (summary_scores or {}).items()
                        if _is_number(value)
                    },
                    "rubricEvaluation": dict(rubric),
                }
            )
        history.sort(key=lambda item: _to_datetime(item.get("timestamp")))
        if profile is None and not history:
            return None
        return {
            "userId": user_id,
            "profile": profile,
            "sessionHistory": history,
        }

    def add_reflection(self, session_id: str, reflection_text: str, coaching_feedback: dict) -> dict | None:
        with SessionLocal() as db:
            row = self._get_session_row(db, session_id)
            if row is None:
                return None
            data = self._read_data(row)
            user_id = str(data.get("userId") or row.user_id)
            self._ensure_user_profile(db, user_id)
            entry = {
                "sessionId": session_id,
                "userId": user_id,
                "reflectionText": reflection_text.strip(),
                "coachingFeedback": dict(coaching_feedback or {}),
                "summaryScores": dict((data.get("scoringResult") or {}).get("summaryScores", {})),
                "createdAt": datetime.now(timezone.utc),
            }
            reflections = list(data.get("reflections") or [])
            reflections.append(entry)
            data["reflections"] = reflections
            row.data_json = _jsonify(data)
            db.add(row)
            db.commit()
            return _jsonify(entry)

    def get_user_reflections(self, user_id: str) -> list[dict]:
        with SessionLocal() as db:
            stmt = select(SessionDB).where(SessionDB.user_id == str(user_id))
            rows = db.execute(stmt).scalars().all()

        entries: list[dict] = []
        for row in rows:
            data = self._read_data(row)
            reflections = list(data.get("reflections") or [])
            for entry in reflections:
                if str(entry.get("userId")) == str(user_id):
                    entries.append(entry)
        entries.sort(key=lambda item: _to_datetime(item.get("createdAt")))
        return _jsonify(entries)

    def summarize_user_reflections(self, user_id: str) -> dict | None:
        entries = self.get_user_reflections(user_id)
        if not entries and self.get_user_profile(user_id) is None:
            return None

        feedback_highlights = []
        for entry in entries:
            coach_feedback = entry.get("coachingFeedback", {})
            coaching_response = str(coach_feedback.get("coachingResponse", "")).strip()
            if coaching_response:
                feedback_highlights.append(coaching_response)

        score_values: dict[str, list[float]] = {}
        for entry in entries:
            for key, value in (entry.get("summaryScores", {}) or {}).items():
                try:
                    score_values.setdefault(str(key), []).append(float(value))
                except Exception:
                    continue

        aggregated_insights = []
        if score_values:
            for score_key, values in score_values.items():
                aggregated_insights.append(f"{score_key} average across reflections: {mean(values):.2f}")
        else:
            aggregated_insights.append(
                "No session scores found yet; submit more analyzed sessions for trend insights."
            )

        return {
            "userId": user_id,
            "totalReflections": len(entries),
            "reflectionEntries": entries[-20:],
            "aggregatedInsights": aggregated_insights[:6],
            "feedbackHighlights": feedback_highlights[:6],
        }

    def register_auth_user(self, user_id: str, password: str, display_name: str | None = None) -> dict:
        user_id = user_id.strip()
        if not user_id:
            raise ValueError("User ID is required")
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters")

        with SessionLocal() as db:
            existing = db.get(UserAccountDB, user_id)
            if existing is not None:
                # Local-dev friendly behavior:
                # register acts as sign-up-or-reset-password for existing user IDs.
                existing.password_hash = hash_password(password)
                if display_name:
                    existing.display_name = display_name
                self._ensure_user_profile(
                    db,
                    user_id=existing.user_id,
                    display_name=existing.display_name or existing.user_id,
                )
                tokens = self._issue_tokens_for_user(
                    db,
                    user_id=existing.user_id,
                    display_name=existing.display_name or existing.user_id,
                )
                db.add(existing)
                db.commit()
                return {
                    **tokens,
                    "user": {
                        "userId": existing.user_id,
                        "displayName": existing.display_name or existing.user_id,
                    },
                }
            password_hash = hash_password(password)
            user_row = UserAccountDB(
                user_id=user_id,
                display_name=display_name or user_id,
                password_hash=password_hash,
            )
            db.add(user_row)
            self._ensure_user_profile(db, user_id=user_id, display_name=display_name or user_id)
            tokens = self._issue_tokens_for_user(db, user_id=user_id, display_name=display_name or user_id)
            db.commit()
            return {
                **tokens,
                "user": {
                    "userId": user_id,
                    "displayName": display_name or user_id,
                },
            }

    def login_auth_user(self, user_id: str, password: str) -> dict:
        user_id = user_id.strip()
        with SessionLocal() as db:
            user_row = db.get(UserAccountDB, user_id)
            if user_row is None or not verify_password(password, user_row.password_hash):
                raise ValueError("Invalid user ID or password")
            tokens = self._issue_tokens_for_user(
                db,
                user_id=user_row.user_id,
                display_name=user_row.display_name or user_row.user_id,
            )
            db.commit()
            return {
                **tokens,
                "user": {
                    "userId": user_row.user_id,
                    "displayName": user_row.display_name or user_row.user_id,
                },
            }

    def refresh_auth_token(self, refresh_token: str) -> dict:
        with SessionLocal() as db:
            try:
                payload = decode_token(refresh_token, expected_type="refresh")
            except Exception as exc:
                raise ValueError("Invalid refresh token") from exc
            user_id = str(payload.get("sub", "")).strip()
            jti = str(payload.get("jti", "")).strip()
            if not user_id or not jti:
                raise ValueError("Invalid refresh token")

            stmt = select(RefreshTokenDB).where(
                RefreshTokenDB.token_jti == jti,
                RefreshTokenDB.user_id == user_id,
            )
            token_row = db.execute(stmt).scalar_one_or_none()
            if token_row is None:
                raise ValueError("Refresh token not found")
            if token_row.revoked:
                raise ValueError("Refresh token revoked")
            if _to_datetime(token_row.expires_at) <= datetime.now(timezone.utc):
                raise ValueError("Refresh token expired")
            if token_row.token_hash != hash_refresh_token(refresh_token):
                raise ValueError("Refresh token mismatch")

            user_row = db.get(UserAccountDB, user_id)
            if user_row is None:
                raise ValueError("User not found")

            # Rotate refresh token and revoke previous one.
            token_row.revoked = True
            token_row.revoked_at = datetime.now(timezone.utc)
            tokens = self._issue_tokens_for_user(
                db,
                user_id=user_row.user_id,
                display_name=user_row.display_name or user_row.user_id,
            )
            token_row.replaced_by_jti = str(tokens.get("refreshTokenJti") or "")
            db.add(token_row)
            db.commit()
            return {
                **tokens,
                "user": {
                    "userId": user_row.user_id,
                    "displayName": user_row.display_name or user_row.user_id,
                },
            }

    def revoke_refresh_token(self, refresh_token: str) -> bool:
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except Exception:
            return False
        user_id = str(payload.get("sub", "")).strip()
        jti = str(payload.get("jti", "")).strip()
        if not user_id or not jti:
            return False

        with SessionLocal() as db:
            stmt = select(RefreshTokenDB).where(
                RefreshTokenDB.token_jti == jti,
                RefreshTokenDB.user_id == user_id,
            )
            token_row = db.execute(stmt).scalar_one_or_none()
            if token_row is None or token_row.revoked:
                return False
            token_row.revoked = True
            token_row.revoked_at = datetime.now(timezone.utc)
            db.add(token_row)
            db.commit()
            return True

    def get_user_by_token(self, token: str) -> dict | None:
        try:
            payload = decode_token(token, expected_type="access")
        except Exception:
            return None
        user_id = str(payload.get("sub", "")).strip()
        if not user_id:
            return None
        with SessionLocal() as db:
            user_row = db.get(UserAccountDB, user_id)
            if user_row is None:
                return None
            return {
                "userId": user_row.user_id,
                "displayName": user_row.display_name or user_row.user_id,
            }

    def revoke_token(self, token: str) -> bool:
        return self.revoke_refresh_token(token)

    def get_auth_user(self, user_id: str) -> dict | None:
        with SessionLocal() as db:
            user_row = db.get(UserAccountDB, str(user_id))
            if user_row is None:
                return None
            return {
                "userId": user_row.user_id,
                "displayName": user_row.display_name or user_row.user_id,
            }

    def create_analysis_job(
        self,
        *,
        session_id: str,
        user_id: str | None,
        payload: dict | None = None,
    ) -> dict:
        with SessionLocal() as db:
            job_id = str(uuid4())
            row = AnalysisJobDB(
                job_id=job_id,
                session_id=session_id,
                user_id=user_id,
                status="queued",
                payload_json=_jsonify(payload or {}),
                result_summary_json={},
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._analysis_job_to_dict(row)

    def mark_analysis_job_running(self, job_id: str, task_id: str | None = None) -> dict | None:
        return self._update_analysis_job(job_id, status="running", task_id=task_id)

    def mark_analysis_job_success(self, job_id: str, result_summary: dict | None = None) -> dict | None:
        return self._update_analysis_job(job_id, status="completed", result_summary=result_summary or {})

    def mark_analysis_job_failed(self, job_id: str, error_message: str) -> dict | None:
        return self._update_analysis_job(job_id, status="failed", error_message=error_message)

    def get_analysis_job(self, job_id: str) -> dict | None:
        with SessionLocal() as db:
            row = db.get(AnalysisJobDB, str(job_id))
            if row is None:
                return None
            return self._analysis_job_to_dict(row)

    def get_latest_analysis_job_for_session(self, session_id: str) -> dict | None:
        with SessionLocal() as db:
            stmt = (
                select(AnalysisJobDB)
                .where(AnalysisJobDB.session_id == str(session_id))
                .order_by(AnalysisJobDB.created_at.desc())
            )
            row = db.execute(stmt).scalars().first()
            if row is None:
                return None
            return self._analysis_job_to_dict(row)

    def _analysis_job_to_dict(self, row: AnalysisJobDB) -> dict:
        return {
            "jobId": row.job_id,
            "sessionId": row.session_id,
            "userId": row.user_id,
            "status": row.status,
            "taskId": row.task_id,
            "errorMessage": row.error_message,
            "payload": _jsonify(row.payload_json or {}),
            "resultSummary": _jsonify(row.result_summary_json or {}),
            "createdAt": row.created_at,
            "updatedAt": row.updated_at,
        }

    def _update_analysis_job(
        self,
        job_id: str,
        *,
        status: str,
        task_id: str | None = None,
        error_message: str | None = None,
        result_summary: dict | None = None,
    ) -> dict | None:
        with SessionLocal() as db:
            row = db.get(AnalysisJobDB, str(job_id))
            if row is None:
                return None
            row.status = status
            if task_id is not None:
                row.task_id = task_id
            if error_message is not None:
                row.error_message = error_message
            if result_summary is not None:
                row.result_summary_json = _jsonify(result_summary)
            row.updated_at = datetime.now(timezone.utc)
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._analysis_job_to_dict(row)

    def _set_session_result(
        self,
        session_id: str,
        field_name: str,
        field_value: dict,
        *,
        status_value: str,
    ) -> dict | None:
        with SessionLocal() as db:
            row = self._get_session_row(db, session_id)
            if row is None:
                return None
            data = self._read_data(row)
            data[field_name] = field_value
            data["status"] = status_value
            row.status = status_value
            row.data_json = _jsonify(data)
            db.add(row)
            db.commit()
            return _jsonify(field_value)

    def _get_session_row(self, db, session_id: str) -> SessionDB | None:
        return db.get(SessionDB, str(session_id))

    def _read_data(self, row: SessionDB) -> dict:
        data = dict(row.data_json or {})
        data.setdefault("sessionId", row.session_id)
        data.setdefault("userId", row.user_id)
        data.setdefault("jobRole", row.job_role)
        data.setdefault("domain", row.domain)
        data.setdefault("status", row.status)
        data.setdefault("startedAt", row.started_at)
        return data

    def _row_to_session_dict(self, row: SessionDB) -> dict:
        data = self._read_data(row)
        data["sessionId"] = row.session_id
        data["userId"] = row.user_id
        data["jobRole"] = row.job_role
        data["domain"] = row.domain
        data["status"] = row.status
        data["startedAt"] = row.started_at
        return _jsonify(data)

    def _issue_tokens_for_user(self, db, *, user_id: str, display_name: str | None) -> dict:
        access_token, access_expires_at = create_access_token(user_id=user_id, display_name=display_name)
        refresh_token, refresh_jti, refresh_expires_at = create_refresh_token(user_id=user_id)
        refresh_row = RefreshTokenDB(
            token_id=str(uuid4()),
            token_jti=refresh_jti,
            user_id=user_id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=refresh_expires_at,
            revoked=False,
            issued_at=datetime.now(timezone.utc),
        )
        db.add(refresh_row)
        return {
            "token": access_token,
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "accessTokenExpiresAt": access_expires_at,
            "expiresIn": access_expires_in_seconds(),
            "refreshTokenJti": refresh_jti,
        }

    def _ensure_user_profile(self, db, user_id: str, display_name: str | None = None) -> None:
        profile = db.get(UserProfileDB, str(user_id))
        if profile is not None:
            if display_name and not profile.display_name:
                profile.display_name = display_name
                profile.updated_at = datetime.now(timezone.utc)
                db.add(profile)
            return
        profile = UserProfileDB(
            user_id=str(user_id),
            display_name=display_name,
            metadata_json={},
            created_at=datetime.now(timezone.utc),
        )
        db.add(profile)

    @staticmethod
    def _build_placeholder_questions(job_role: str, domain: str) -> list[dict]:
        role = (job_role or "this role").strip()
        industry = (domain or "this domain").strip()
        return [
            {
                "questionId": "q1",
                "questionText": (
                    f"Hi, great to meet you. To start, can you briefly introduce yourself and your experience as a {role}?"
                ),
            },
            {
                "questionId": "q2",
                "questionText": (
                    f"What interests you most about this {role} opportunity in {industry}, and what impact do you want to make?"
                ),
            },
            {
                "questionId": "q3",
                "questionText": (
                    f"Let's go deeper technically: describe a recent project in {industry} where you made an important design decision."
                ),
            },
            {
                "questionId": "q4",
                "questionText": (
                    "Tell me about a time you disagreed with a teammate or stakeholder. How did you resolve it and what changed?"
                ),
            },
            {
                "questionId": "q5",
                "questionText": (
                    f"If you joined tomorrow as a {role}, what would your 30-60-90 day plan look like?"
                ),
            },
        ]


session_store = SessionStore()


def _is_number(value: object) -> bool:
    try:
        float(value)
        return True
    except Exception:
        return False


def _jsonify(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonify(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonify(item) for item in value]
    return value


def _to_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except Exception:
            pass
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)
