import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { buildPerformanceTrend, summarizeTrendDirection } from "../utils/progressTrend";
import { useAuth } from "../context/AuthContext";
import styles from "./ProgressDashboard.module.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function ProgressDashboard() {
  const { userId } = useParams();
  const navigate = useNavigate();
  const { token, user, logout } = useAuth();
  const [historyPayload, setHistoryPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    async function loadHistory() {
      setLoading(true);
      setError("");
      try {
        const response = await fetch(`${API_BASE_URL}/users/${userId}/performance-history`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        if (response.status === 401) {
          throw new Error("SESSION_EXPIRED");
        }
        if (!response.ok) {
          throw new Error(`Request failed: ${response.status}`);
        }
        const payload = await response.json();
        if (mounted) {
          setHistoryPayload(payload);
        }
      } catch (err) {
        if (mounted) {
          if (String(err.message || "") === "SESSION_EXPIRED") {
            logout();
            navigate("/auth", { replace: true });
            return;
          }
          setError(err.message || "Unable to load performance history.");
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }
    loadHistory();
    return () => {
      mounted = false;
    };
  }, [token, userId, logout, navigate]);

  const trendRows = useMemo(
    () => buildPerformanceTrend(historyPayload?.sessionHistory || []),
    [historyPayload]
  );
  const trendDirection = summarizeTrendDirection(trendRows);

  if (loading) {
    return <main className={styles.stateView}>Loading progress dashboard...</main>;
  }
  if (error) {
    return (
      <main className={styles.stateView}>
        <p>{error}</p>
        <Link to="/app">Back</Link>
      </main>
    );
  }

  return (
    <main className={styles.shell}>
      <header className={styles.headerRow}>
        <div>
          <p className={styles.tag}>Progress Dashboard</p>
          <h1>Performance Trend for {user?.displayName || userId}</h1>
          <p className={styles.metaText}>
            Trend status: <strong>{trendDirection.replace("_", " ")}</strong>
          </p>
        </div>
        <Link className={styles.backLink} to="/app">
          Back
        </Link>
      </header>

      <section className={styles.chartCard} data-testid="progress-trend-chart">
        <h2>Session Score Trend</h2>
        {trendRows.length ? (
          <div className={styles.chartBody}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trendRows} margin={{ top: 10, right: 24, left: 0, bottom: 6 }}>
                <CartesianGrid strokeDasharray="4 4" stroke="#cbd5e1" />
                <XAxis dataKey="order" label={{ value: "Session #", position: "insideBottom", offset: -4 }} />
                <YAxis domain={[0, 100]} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="overallPerformanceScore" stroke="#0f766e" strokeWidth={2.4} dot />
                <Line type="monotone" dataKey="engagementScore" stroke="#2563eb" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="confidenceScore" stroke="#f97316" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p>No history yet. Complete and score more sessions to view trends.</p>
        )}
      </section>

      <section className={styles.tableCard}>
        <h2>Session History</h2>
        {trendRows.length ? (
          <div className={styles.tableWrapper}>
            <table>
              <thead>
                <tr>
                  <th>Session</th>
                  <th>Date</th>
                  <th>Overall</th>
                  <th>Engagement</th>
                  <th>Confidence</th>
                  <th>Speech</th>
                </tr>
              </thead>
              <tbody>
                {trendRows.map((row) => (
                  <tr key={row.sessionId}>
                    <td>{row.sessionId}</td>
                    <td>{row.timestamp ? new Date(row.timestamp).toLocaleString() : "-"}</td>
                    <td>{row.overallPerformanceScore.toFixed(1)}</td>
                    <td>{row.engagementScore.toFixed(1)}</td>
                    <td>{row.confidenceScore.toFixed(1)}</td>
                    <td>{row.speechFluency.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </main>
  );
}

export default ProgressDashboard;
