import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import styles from "./ReflectiveLearningPanel.module.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function ReflectiveLearningPanel() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const { token, logout } = useAuth();
  const [userId, setUserId] = useState("");
  const [reflectionText, setReflectionText] = useState("");
  const [coachResult, setCoachResult] = useState(null);
  const [summaryPayload, setSummaryPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    async function loadContext() {
      setLoading(true);
      setError("");
      try {
        let statusResp = await fetch(`${API_BASE_URL}/app/me/sessions/${sessionId}/status`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        if (statusResp.status === 401) {
          throw new Error("SESSION_EXPIRED");
        }
        if (!statusResp.ok) {
          statusResp = await fetch(`${API_BASE_URL}/interviews/${sessionId}/status`);
        }
        if (!statusResp.ok) {
          throw new Error(`Unable to fetch session status (${statusResp.status})`);
        }
        const statusData = await statusResp.json();
        if (!mounted) {
          return;
        }
        setUserId(statusData.userId);

        const summaryResp = await fetch(`${API_BASE_URL}/reflective/${statusData.userId}/summaries`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        if (summaryResp.status === 401) {
          throw new Error("SESSION_EXPIRED");
        }
        if (summaryResp.ok) {
          const summary = await summaryResp.json();
          if (mounted) {
            setSummaryPayload(summary);
          }
        }
      } catch (err) {
        if (mounted) {
          if (String(err.message || "") === "SESSION_EXPIRED") {
            logout();
            navigate("/auth", { replace: true });
            return;
          }
          setError(err.message || "Unable to load reflective panel context.");
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }
    loadContext();
    return () => {
      mounted = false;
    };
  }, [sessionId, token, logout, navigate]);

  async function submitReflection(event) {
    event.preventDefault();
    if (!reflectionText.trim()) {
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/reflective/${sessionId}/responses`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ reflectionText: reflectionText.trim() }),
      });
      if (response.status === 401) {
        throw new Error("SESSION_EXPIRED");
      }
      if (!response.ok) {
        throw new Error(`Reflection request failed (${response.status})`);
      }
      const data = await response.json();
      setCoachResult(data);
      setReflectionText("");

      if (userId) {
        const summaryResp = await fetch(`${API_BASE_URL}/reflective/${userId}/summaries`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        if (summaryResp.status === 401) {
          throw new Error("SESSION_EXPIRED");
        }
        if (summaryResp.ok) {
          const summary = await summaryResp.json();
          setSummaryPayload(summary);
        }
      }
    } catch (err) {
      if (String(err.message || "") === "SESSION_EXPIRED") {
        logout();
        navigate("/auth", { replace: true });
        return;
      }
      setError(err.message || "Unable to submit reflection.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return <main className={styles.stateView}>Loading reflective learning panel...</main>;
  }

  return (
    <main className={styles.shell}>
      <header className={styles.headerRow}>
        <div>
          <p className={styles.tag}>Reflective Learning</p>
          <h1>Session {sessionId}</h1>
          <p className={styles.metaText}>User: {userId || "Unknown"}</p>
        </div>
        <div className={styles.headerActions}>
          {userId ? (
            <Link className={styles.secondaryLink} to={`/progress/${userId}`}>
              View Progress
            </Link>
          ) : null}
          <Link className={styles.backLink} to="/app">
            Back
          </Link>
        </div>
      </header>

      <section className={styles.formCard}>
        <h2>Reflect on Your Performance</h2>
        <p>
          Write what felt strong or weak in this interview. The system will generate reflective coaching guidance.
        </p>
        <form onSubmit={submitReflection}>
          <textarea
            value={reflectionText}
            onChange={(event) => setReflectionText(event.target.value)}
            placeholder="Example: I explained architecture clearly but my pacing slowed on follow-up questions..."
            rows={6}
          />
          <div className={styles.formActions}>
            <button type="submit" disabled={submitting}>
              {submitting ? "Submitting..." : "Submit Reflection"}
            </button>
          </div>
        </form>
      </section>

      {error ? (
        <section className={styles.errorCard}>
          <p>{error}</p>
        </section>
      ) : null}

      {coachResult ? (
        <section className={styles.coachCard}>
          <h2>Reflective Coach Suggestion</h2>
          <p>{coachResult.coachingFeedback?.coachingResponse || "No coaching response available."}</p>
          <h3>Focus Areas</h3>
          <ul>
            {(coachResult.coachingFeedback?.focusAreas || []).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <h3>Next Session Plan</h3>
          <ul>
            {(coachResult.coachingFeedback?.nextSessionPlan || []).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {summaryPayload ? (
        <section className={styles.summaryCard}>
          <h2>Reflection History & Aggregated Insights</h2>
          <p>Total reflections: {summaryPayload.totalReflections}</p>
          <h3>Insights</h3>
          <ul>
            {(summaryPayload.aggregatedInsights || []).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <h3>Feedback Highlights</h3>
          <ul>
            {(summaryPayload.feedbackHighlights || []).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </main>
  );
}

export default ReflectiveLearningPanel;
