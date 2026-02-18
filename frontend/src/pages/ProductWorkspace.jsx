import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import styles from "./ProductWorkspace.module.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function ProductWorkspace() {
  const navigate = useNavigate();
  const { token, user, logout } = useAuth();
  const [sessions, setSessions] = useState([]);
  const [jobRole, setJobRole] = useState("Backend Engineer");
  const [domain, setDomain] = useState("FinTech");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const userId = user?.userId || "";
  const displayName = user?.displayName || userId || "User";

  function toStatusText(status) {
    return String(status || "unknown")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (match) => match.toUpperCase());
  }

  function getStatusClassName(status) {
    const normalized = String(status || "").toLowerCase();
    if (normalized.includes("failed")) {
      return styles.statusFailed;
    }
    if (normalized.includes("ready") || normalized.includes("scored") || normalized.includes("completed")) {
      return styles.statusReady;
    }
    if (normalized.includes("queued") || normalized.includes("running") || normalized.includes("uploaded")) {
      return styles.statusProcessing;
    }
    return styles.statusNeutral;
  }

  const authHeaders = useMemo(
    () => ({
      Authorization: `Bearer ${token}`,
    }),
    [token]
  );

  async function loadSessions() {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/app/me/sessions`, {
        headers: authHeaders,
      });
      if (response.status === 401) {
        throw new Error("SESSION_EXPIRED");
      }
      if (!response.ok) {
        throw new Error(`Unable to load sessions (${response.status})`);
      }
      const payload = await response.json();
      setSessions(payload);
    } catch (err) {
      if (String(err.message || "") === "SESSION_EXPIRED") {
        logout();
        navigate("/auth", { replace: true });
        return;
      }
      setError(err.message || "Failed to load sessions.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function createSession(event) {
    event.preventDefault();
    if (!jobRole.trim() || !domain.trim()) {
      setError("Job role and domain are required.");
      return;
    }
    setCreating(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(`${API_BASE_URL}/app/me/sessions/start`, {
        method: "POST",
        headers: {
          ...authHeaders,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          jobRole: jobRole.trim(),
          domain: domain.trim(),
        }),
      });
      if (response.status === 401) {
        throw new Error("SESSION_EXPIRED");
      }
      if (!response.ok) {
        throw new Error(`Failed to create session (${response.status})`);
      }
      const created = await response.json();
      setMessage(`Session created: ${created.sessionId}`);
      await loadSessions();
    } catch (err) {
      if (String(err.message || "") === "SESSION_EXPIRED") {
        logout();
        navigate("/auth", { replace: true });
        return;
      }
      setError(err.message || "Could not create session.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className={styles.shell}>
      <header className={styles.headerRow}>
        <div>
          <p className={styles.kicker}>InterviewInsight Workspace</p>
          <h1>Welcome, {displayName}</h1>
          <p className={styles.subtitle}>
            Create sessions and review analytics generated from live interview recordings.
          </p>
        </div>
        <div className={styles.headerActions}>
          <Link className={styles.secondaryAction} to="/interview/live">
            Start Live Interview
          </Link>
          {userId ? (
            <Link className={styles.secondaryAction} to={`/progress/${userId}`}>
              My Progress
            </Link>
          ) : (
            <span className={styles.secondaryActionDisabled}>My Progress</span>
          )}
          <button type="button" className={styles.secondaryAction} onClick={loadSessions} disabled={loading}>
            {loading ? "Refreshing..." : "Refresh"}
          </button>
          <button
            type="button"
            className={styles.logoutButton}
            onClick={() => {
              logout();
              navigate("/auth", { replace: true });
            }}
          >
            Logout
          </button>
        </div>
      </header>

      <section className={styles.card}>
        <h2>Create New Interview Session</h2>
        <p className={styles.cardNote}>Sessions are analyzed automatically after you complete a live interview.</p>
        <form className={styles.form} onSubmit={createSession}>
          <label htmlFor="job-role">Job Role</label>
          <input
            id="job-role"
            value={jobRole}
            onChange={(event) => setJobRole(event.target.value)}
            placeholder="Backend Engineer"
            required
          />

          <label htmlFor="domain">Domain</label>
          <input
            id="domain"
            value={domain}
            onChange={(event) => setDomain(event.target.value)}
            placeholder="FinTech"
            required
          />
          <button type="submit" disabled={creating}>
            {creating ? "Creating..." : "Create Session"}
          </button>
        </form>
      </section>

      <section className={styles.card}>
        <h2>My Sessions</h2>
        {loading ? <p>Loading sessions...</p> : null}
        {!loading && sessions.length === 0 ? <p>No sessions yet. Create one to begin.</p> : null}
        <div className={styles.sessionList}>
          {sessions.map((session) => (
            <article key={session.sessionId} className={styles.sessionItem}>
              <div>
                <p className={styles.sessionTitle}>
                  {session.jobRole} ({session.domain})
                </p>
                <p className={styles.sessionMeta}>{session.sessionId}</p>
                <div className={styles.sessionMetaRow}>
                  <span>{session.startedAt ? new Date(session.startedAt).toLocaleString() : "Unknown time"}</span>
                  <span className={`${styles.statusPill} ${getStatusClassName(session.status)}`}>
                    {toStatusText(session.status)}
                  </span>
                </div>
              </div>
              <div className={styles.sessionActions}>
                <Link className={styles.linkButton} to={`/dashboard/${session.sessionId}`}>
                  Dashboard
                </Link>
                <Link className={styles.linkButton} to={`/reflective/${session.sessionId}`}>
                  Reflect
                </Link>
              </div>
            </article>
          ))}
        </div>
      </section>

      {error ? <section className={styles.errorBox}>{error}</section> : null}
      {message ? <section className={styles.successBox}>{message}</section> : null}
    </main>
  );
}

export default ProductWorkspace;
