import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import styles from "./AuthPage.module.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function AuthPage() {
  const navigate = useNavigate();
  const { setAuthSession } = useAuth();
  const [mode, setMode] = useState("login");
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    const endpoint = mode === "register" ? "/auth/register" : "/auth/login";
    const body = {
      userId: userId.trim(),
      password,
    };
    if (mode === "register" && displayName.trim()) {
      body.displayName = displayName.trim();
    }
    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        let detail = `Request failed (${response.status})`;
        try {
          const payload = await response.json();
          if (payload?.detail) {
            detail = String(payload.detail);
          }
        } catch {
          try {
            const fallbackText = await response.text();
            if (fallbackText?.trim()) {
              detail = fallbackText.trim();
            }
          } catch {
            // Ignore parse failure.
          }
        }
        throw new Error(detail);
      }
      const payload = await response.json();
      setAuthSession(payload.accessToken || payload.token, payload.user, payload.refreshToken || "");
      navigate("/app", { replace: true });
    } catch (err) {
      setError(err.message || "Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className={styles.shell}>
      <section className={styles.layout}>
        <section className={styles.card}>
          <p className={styles.kicker}>Secure Workspace Access</p>
          <h1>Sign in to your workspace</h1>
          <p className={styles.subtitle}>
            Create your own account to save interview sessions, analytics, and reflections.
          </p>
          <div className={styles.taglineBlock}>
            <p className={styles.taglineLabel}>AI Interview Assistant</p>
            <h2 className={styles.taglineTitle}>Practice. Improve. Get Hired.</h2>
            <span className={styles.taglinePulse} />
          </div>

          <div className={styles.modeTabs}>
            <button
              type="button"
              onClick={() => setMode("login")}
              className={mode === "login" ? styles.active : ""}
            >
              Login
            </button>
            <button
              type="button"
              onClick={() => setMode("register")}
              className={mode === "register" ? styles.active : ""}
            >
              Register
            </button>
          </div>

          <form onSubmit={onSubmit} className={styles.form}>
            <label htmlFor="user-id">User ID</label>
            <input
              id="user-id"
              value={userId}
              onChange={(event) => setUserId(event.target.value)}
              placeholder="your-user-id"
              required
            />

            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Your password"
              required
            />

            {mode === "register" ? (
              <>
                <label htmlFor="display-name">Display name (optional)</label>
                <input
                  id="display-name"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  placeholder="Your name"
                />
              </>
            ) : null}

            {error ? <p className={styles.error}>{error}</p> : null}

            <button type="submit" disabled={loading}>
              {loading ? "Please wait..." : mode === "register" ? "Create Account" : "Sign In"}
            </button>
          </form>
        </section>
      </section>
    </main>
  );
}

export default AuthPage;
