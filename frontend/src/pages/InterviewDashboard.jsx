import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import EmotionLegend, { EMOTION_COLORS } from "../components/EmotionLegend";
import ReportGenerator from "../components/ReportGenerator";
import ScoreCard from "../components/ScoreCard";
import SegmentCard from "../components/SegmentCard";
import TimelineChart from "../components/TimelineChart";
import { useAuth } from "../context/AuthContext";
import styles from "./InterviewDashboard.module.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const ANALYSIS_POLL_INITIAL_DELAY_MS = 2500;
const ANALYSIS_POLL_MAX_DELAY_MS = 12000;
const ANALYSIS_MAX_POLL_ATTEMPTS = 120;
const REPORT_CHART_SELECTORS = {
  emotionTimeline: '[data-report-chart="emotionTimeline"]',
  gazeHeadPoseTimeline: '[data-report-chart="gazeHeadPoseTimeline"]',
  speechTimeline: '[data-report-chart="speechTimeline"]',
  engagementTimeline: '[data-report-chart="engagementTimeline"]',
};

function deriveSegmentRecommendation(segment) {
  const engagement = Number(segment?.engagementScore || 0);
  const fluency = Number(segment?.speechFluency || 0);
  const relevance = Number(segment?.textRelevanceScore || 0);
  const dominantEmotion = String(segment?.dominantEmotion || "neutral").toLowerCase();

  if (engagement < 55) {
    return "Increase eye contact and reduce off-screen gaze.";
  }
  if (fluency < 55) {
    return "Slow down slightly and minimize long pauses.";
  }
  if (relevance < 60) {
    return "Use more role-specific examples with measurable outcomes.";
  }
  if (dominantEmotion === "sad" || dominantEmotion === "fear") {
    return "Keep tone steady and maintain confident delivery.";
  }
  return "Strong segment. Keep this structure in future answers.";
}

function deriveSegmentFeedback(segment) {
  const engagement = Number(segment?.engagementScore || 0);
  const fluency = Number(segment?.speechFluency || 0);
  const relevance = Number(segment?.textRelevanceScore || 0);
  const emotion = String(segment?.dominantEmotion || "neutral").toLowerCase();
  const mistakes = [];
  const improvements = [];

  if (engagement < 55) {
    mistakes.push("Low engagement and camera connection in this answer.");
    improvements.push("Keep eye focus near camera and reduce off-screen gaze.");
  }
  if (fluency < 55) {
    mistakes.push("Speech fluency dropped with pauses or rushed pacing.");
    improvements.push("Use shorter sentence blocks and controlled pauses.");
  }
  if (relevance < 60) {
    mistakes.push("Answer relevance was weak for the question intent.");
    improvements.push("Use role-specific examples and measurable outcomes.");
  }
  if (emotion === "fear" || emotion === "sad") {
    mistakes.push("Emotional tone reduced confidence perception.");
    improvements.push("Keep steady tone and close with a confident summary line.");
  }

  if (!mistakes.length) {
    mistakes.push("No major issue detected in this segment.");
  }
  if (!improvements.length) {
    improvements.push("Maintain this structure and delivery style.");
  }

  return { mistakes, improvements };
}

function deriveSegmentCoaching(segment) {
  const engagement = Number(segment?.engagementScore || 0);
  const fluency = Number(segment?.speechFluency || 0);
  const relevance = Number(segment?.textRelevanceScore || 0);
  const emotion = String(segment?.dominantEmotion || "neutral").toLowerCase();
  const strengths = [];
  const hurts = [];

  if (engagement >= 70) {
    strengths.push("Maintained stable camera presence and engagement.");
  } else {
    hurts.push("Camera connection dropped and reduced interviewer engagement.");
  }

  if (fluency >= 70) {
    strengths.push("Speech pace was clear and easy to follow.");
  } else {
    hurts.push("Pacing or pauses disrupted flow and clarity.");
  }

  if (relevance >= 70) {
    strengths.push("Answer stayed relevant to the role context.");
  } else {
    hurts.push("Key points were not tightly mapped to the question intent.");
  }

  if (emotion === "fear" || emotion === "sad") {
    hurts.push("Emotional tone reduced confidence perception.");
  } else {
    strengths.push("Delivery tone stayed mostly composed.");
  }

  if (!strengths.length) {
    strengths.push("You completed the response window end-to-end.");
  }
  if (!hurts.length) {
    hurts.push("No major blocker detected in this answer segment.");
  }

  const rewriteLine =
    relevance < 70
      ? "Rewrite to practice: \"For this question, I solved [specific problem] by doing [clear actions], which led to [measurable outcome], and I would apply the same approach here.\""
      : fluency < 70
        ? "Rewrite to practice: \"My approach had three parts: first [context], second [action], third [result]. The key impact was [metric].\""
        : "Rewrite to practice: \"I identified [problem], implemented [solution], and achieved [result]. This is relevant because [role-specific reason].\"";

  return { strengths, hurts, rewriteLine };
}

function InterviewDashboard() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const { token, logout } = useAuth();
  const [searchParams] = useSearchParams();
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [analysis, setAnalysis] = useState(null);
  const [advancedInsights, setAdvancedInsights] = useState(null);
  const [sessionUserId, setSessionUserId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pendingMessage, setPendingMessage] = useState("");

  const [showVideo, setShowVideo] = useState(true);
  const [showAudio, setShowAudio] = useState(true);
  const [showFused, setShowFused] = useState(true);

  const [selectedTimestamp, setSelectedTimestamp] = useState(0);
  const [videoBlobUrl, setVideoBlobUrl] = useState("");
  const [videoFetchError, setVideoFetchError] = useState("");
  const [activeSegmentId, setActiveSegmentId] = useState("");
  const [sessionQuestions, setSessionQuestions] = useState([]);
  const [playWindow, setPlayWindow] = useState(null);
  const videoRef = useRef(null);
  const logoutRef = useRef(logout);
  const navigateRef = useRef(navigate);

  useEffect(() => {
    logoutRef.current = logout;
  }, [logout]);

  useEffect(() => {
    navigateRef.current = navigate;
  }, [navigate]);

  function retryAnalysisLoad() {
    setError("");
    setPendingMessage("Retrying analysis...");
    setLoading(true);
    setRefreshNonce((value) => value + 1);
  }

  useEffect(() => {
    let mounted = true;
    let retryTimer = null;

    async function loadAnalysis(attempt = 0) {
      let keepLoading = false;
      const isRetry = attempt > 0;
      if (!isRetry) {
        setLoading(true);
        setError("");
        setPendingMessage("");
      }
      try {
        let job = null;
        let hasJobEndpoint = false;
        let pendingJobResponse = await fetch(`${API_BASE_URL}/analysis/${sessionId}/job`, {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        });
        if (!pendingJobResponse.ok && pendingJobResponse.status !== 401) {
          pendingJobResponse = await fetch(`${API_BASE_URL}/analysis/${sessionId}/job`);
        }
        if (pendingJobResponse.status === 401) {
          throw new Error("SESSION_EXPIRED");
        }
        if (pendingJobResponse.ok) {
          hasJobEndpoint = true;
          job = await pendingJobResponse.json();
          const jobStatus = String(job.status || "").toLowerCase();
          if (jobStatus === "failed") {
            throw new Error(job.errorMessage || "Analysis job failed");
          }
          if (["queued", "running", "started", "pending"].includes(jobStatus)) {
            if (attempt >= ANALYSIS_MAX_POLL_ATTEMPTS) {
              throw new Error("Analysis is taking too long. Please check if Celery worker is running.");
            }
            if (mounted) {
              const nextAttempt = attempt + 1;
              const nextDelay = Math.min(
                ANALYSIS_POLL_MAX_DELAY_MS,
                ANALYSIS_POLL_INITIAL_DELAY_MS + (nextAttempt - 1) * 500,
              );
              setPendingMessage(`Analysis is ${jobStatus}. Refreshing automatically...`);
              setLoading(true);
              keepLoading = true;
              retryTimer = window.setTimeout(() => {
                void loadAnalysis(nextAttempt);
              }, nextDelay);
            }
            return;
          }
        } else if (pendingJobResponse.status === 404) {
          hasJobEndpoint = false;
        }

        let response = await fetch(`${API_BASE_URL}/app/me/sessions/${sessionId}/analysis`, {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        });
        if (response.status === 401) {
          throw new Error("SESSION_EXPIRED");
        }
        if (!response.ok) {
          if (token) {
            if (response.status === 404 && !hasJobEndpoint) {
              throw new Error("No analysis job found for this session yet. End interview and run analysis first.");
            }
          } else {
            response = await fetch(`${API_BASE_URL}/analysis/${sessionId}/results`);
          }
        }
        if (!response.ok) {
          if (job && String(job.status || "").toLowerCase() === "completed") {
            throw new Error("Analysis job completed but result payload was not found. Check worker logs.");
          }
          throw new Error("Analysis is not available yet.");
        }

        const data = await response.json();
        try {
          let statusResp = await fetch(`${API_BASE_URL}/app/me/sessions/${sessionId}/status`, {
            headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          });
          if (statusResp.status === 401) {
            throw new Error("SESSION_EXPIRED");
          }
          if (!statusResp.ok) {
            statusResp = await fetch(`${API_BASE_URL}/interviews/${sessionId}/status`);
          }
          if (statusResp.ok) {
            const statusData = await statusResp.json();
            if (mounted) {
              setSessionUserId(statusData.userId || "");
            }
          }
        } catch {
          // Ignore status fetch errors and keep dashboard available.
        }
        let explainData = null;
        try {
          let explainResponse = await fetch(`${API_BASE_URL}/app/me/sessions/${sessionId}/scores/explain`, {
            headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          });
          if (explainResponse.status === 401) {
            throw new Error("SESSION_EXPIRED");
          }
          if (!explainResponse.ok) {
            explainResponse = await fetch(`${API_BASE_URL}/scores/${sessionId}/explain`);
          }
          if (explainResponse.ok) {
            explainData = await explainResponse.json();
          }
        } catch {
          explainData = null;
        }
        if (mounted) {
          setAnalysis(data);
          setAdvancedInsights(explainData);
        }
      } catch (err) {
        if (mounted) {
          if (String(err.message || "") === "SESSION_EXPIRED") {
            logoutRef.current();
            navigateRef.current("/auth", { replace: true });
            return;
          }
          setError(err.message || "Unable to load analysis results");
        }
      } finally {
        if (mounted && !keepLoading) {
          setLoading(false);
        }
      }
    }

    loadAnalysis();
    return () => {
      mounted = false;
      if (retryTimer) {
        window.clearTimeout(retryTimer);
      }
    };
  }, [sessionId, token, refreshNonce]);

  useEffect(() => {
    let mounted = true;
    setSessionQuestions([]);

    async function loadSessionQuestions() {
      if (!sessionId) {
        return;
      }
      try {
        const response = await fetch(`${API_BASE_URL}/interviews/${sessionId}/questions`, {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        });
        if (!response.ok) {
          return;
        }
        const data = await response.json();
        if (mounted && Array.isArray(data)) {
          setSessionQuestions(data);
        }
      } catch {
        // Optional enrichment only.
      }
    }

    void loadSessionQuestions();
    return () => {
      mounted = false;
    };
  }, [sessionId, token]);

  useEffect(() => {
    if (!playWindow || !videoRef.current) {
      return;
    }

    const intervalId = window.setInterval(() => {
      if (!videoRef.current) {
        return;
      }
      if (videoRef.current.currentTime >= playWindow.end) {
        videoRef.current.pause();
        setPlayWindow(null);
      }
    }, 160);

    return () => window.clearInterval(intervalId);
  }, [playWindow]);

  const queryVideoUrl = searchParams.get("videoUrl") || "";
  const videoUrl =
    queryVideoUrl ||
    videoBlobUrl ||
    (analysis?.videoFilePath?.startsWith("http") ? analysis.videoFilePath : "");

  useEffect(() => {
    let mounted = true;
    let createdObjectUrl = "";

    async function loadSessionVideo() {
      if (!sessionId || !token || queryVideoUrl) {
        return;
      }
      try {
        const response = await fetch(`${API_BASE_URL}/app/me/sessions/${sessionId}/video`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) {
          if (response.status !== 404 && mounted) {
            setVideoFetchError(`Unable to load session video (${response.status})`);
          }
          return;
        }
        const blob = await response.blob();
        createdObjectUrl = URL.createObjectURL(blob);
        if (mounted) {
          setVideoBlobUrl((previous) => {
            if (previous && previous !== createdObjectUrl) {
              URL.revokeObjectURL(previous);
            }
            return createdObjectUrl;
          });
          setVideoFetchError("");
          createdObjectUrl = "";
        }
      } catch {
        if (mounted) {
          setVideoFetchError("Unable to load session video.");
        }
      }
    }

    void loadSessionVideo();
    return () => {
      mounted = false;
      if (createdObjectUrl) {
        URL.revokeObjectURL(createdObjectUrl);
      }
    };
  }, [sessionId, token, queryVideoUrl]);

  useEffect(() => {
    return () => {
      if (videoBlobUrl) {
        URL.revokeObjectURL(videoBlobUrl);
      }
    };
  }, [videoBlobUrl]);

  const chartData = useMemo(() => {
    if (!analysis?.timelineArrays) {
      return {
        emotionTimeline: [],
        engagementTimeline: [],
        speechTimeline: [],
        gazeTimeline: [],
      };
    }

    const emotionTimeline = analysis.timelineArrays.emotionTimeline.map((item) => ({
      timestamp: item.timestamp,
      ...item.emotionScores,
      dominantEmotion: item.dominantEmotion,
    }));

    return {
      emotionTimeline,
      engagementTimeline: analysis.timelineArrays.engagementTimeline || [],
      speechTimeline: analysis.timelineArrays.speechTimeline || [],
      gazeTimeline: analysis.timelineArrays.gazeHeadPoseTimeline || [],
    };
  }, [analysis]);

  function playFromTimestamp(timestamp) {
    if (!videoRef.current || !videoUrl) {
      return;
    }
    const video = videoRef.current;
    const target = Math.max(0, Number(timestamp || 0));
    const startPlayback = () => {
      const duration = Number.isFinite(video.duration) ? Number(video.duration) : target;
      video.currentTime = Math.min(target, Math.max(0, duration));
      video.play().catch(() => {
        setError("Browser blocked autoplay. Use controls in the video player.");
      });
    };

    if (video.readyState < 1) {
      video.addEventListener("loadedmetadata", startPlayback, { once: true });
      video.load();
      return;
    }
    startPlayback();
  }

  function replaySegment(start, end, segmentId) {
    setSelectedTimestamp(start);
    if (segmentId) {
      setActiveSegmentId(segmentId);
    }
    setPlayWindow({ start, end });
    playFromTimestamp(start);
  }

  function playSelectedTimestamp() {
    if (!videoUrl) {
      setVideoFetchError("No session video found for playback.");
      return;
    }
    setVideoFetchError("");
    playFromTimestamp(selectedTimestamp);
  }

  if (loading) {
    return <main className={styles.stateView}>{pendingMessage || "Loading dashboard..."}</main>;
  }

  if (error) {
    const normalizedError = String(error || "").toLowerCase();
    const workerStalled =
      normalizedError.includes("taking too long") ||
      normalizedError.includes("analysis job failed") ||
      normalizedError.includes("result payload was not found");

    if (workerStalled) {
      return (
        <main className={styles.stateView}>
          <section className={styles.workerStalledCard}>
            <h2>Worker offline or queue stalled</h2>
            <p>{error}</p>
            <p className={styles.workerHint}>
              Confirm Redis and Celery worker are running, then retry.
            </p>
            <div className={styles.workerActions}>
              <button type="button" onClick={retryAnalysisLoad}>
                Retry now
              </button>
              <Link to="/">Back</Link>
            </div>
          </section>
        </main>
      );
    }

    return (
      <main className={styles.stateView}>
        <p>{error}</p>
        <Link to="/">Back</Link>
      </main>
    );
  }

  if (!analysis) {
    return <main className={styles.stateView}>No analysis found.</main>;
  }

  const summary = analysis.summaryScores;
  const sessionMeta = analysis.sessionMeta;
  const segmentLabels = analysis.segmentLabels || [];
  const feedbackSummary = analysis.feedbackSummary || {
    strengths: [],
    improvements: [],
    suggestedFeedbackText: "",
  };
  const segmentInsights = segmentLabels.map((segment) => ({
    ...segment,
    recommendation: deriveSegmentRecommendation(segment),
    feedback: deriveSegmentFeedback(segment),
    coaching: deriveSegmentCoaching(segment),
  }));
  const segmentInsightsWithContext = segmentInsights.map((segment, index) => ({
    ...segment,
    questionText: sessionQuestions[index]?.questionText || "",
    answerLabel: `Answer ${index + 1}`,
  }));
  const activeSegment =
    segmentInsightsWithContext.find((segment) => segment.segmentId === activeSegmentId) ||
    segmentInsightsWithContext[0] ||
    null;
  const topWeakSegments = [...segmentInsightsWithContext]
    .sort((a, b) => {
      const scoreA = Number(a.engagementScore || 0) + Number(a.speechFluency || 0) + Number(a.textRelevanceScore || 0);
      const scoreB = Number(b.engagementScore || 0) + Number(b.speechFluency || 0) + Number(b.textRelevanceScore || 0);
      return scoreA - scoreB;
    })
    .slice(0, 3);
  const topStrongSegment = [...segmentInsightsWithContext]
    .sort((a, b) => {
      const scoreA = Number(a.engagementScore || 0) + Number(a.speechFluency || 0) + Number(a.textRelevanceScore || 0);
      const scoreB = Number(b.engagementScore || 0) + Number(b.speechFluency || 0) + Number(b.textRelevanceScore || 0);
      return scoreB - scoreA;
    })[0];
  const topTakeaways = [
    topStrongSegment
      ? `${topStrongSegment.answerLabel} (${topStrongSegment.startTime.toFixed(1)}s-${topStrongSegment.endTime.toFixed(1)}s) is your strongest pattern. Reuse this structure in future answers.`
      : null,
    summary.speechFluency < 70
      ? "Biggest gain area: speech flow. Use shorter statements and one-beat pauses between ideas."
      : "Speech delivery is stable; keep this pace while adding more concrete outcomes.",
    topWeakSegments[0]
      ? `${topWeakSegments[0].answerLabel} needs immediate improvement on engagement/relevance. Practice this segment first in your next mock round.`
      : feedbackSummary.improvements[0] || null,
  ].filter(Boolean).slice(0, 3);
  const evidenceClips = topWeakSegments.map((segment) => {
    const rawStart = Number(segment.startTime || 0);
    const rawEnd = Number(segment.endTime || 0);
    const clipStart = Math.max(0, rawStart - 2);
    const clipEnd = rawEnd > rawStart ? rawEnd + 2 : rawStart + 10;
    return {
      segmentId: segment.segmentId,
      answerLabel: segment.answerLabel,
      issue: segment.coaching.hurts[0] || segment.recommendation,
      clipStart,
      clipEnd,
    };
  });
  const improvementPlan = [
    summary.engagementScore < 70 ? "Practice camera-focused speaking to improve engagement consistency." : null,
    summary.speechFluency < 70 ? "Use concise sentence blocks and 1-second micro-pauses between key points." : null,
    summary.confidenceScore < 70 ? "Answer with structured STAR format and finish with impact metrics." : null,
    summary.emotionalStability < 70 ? "Reduce rushed pacing and maintain steady tone across answers." : null,
    ...topWeakSegments.map((segment) => `For ${segment.label}: ${segment.recommendation}`),
  ].filter(Boolean).slice(0, 5);
  const summaryNarrative = `Overall performance is ${Number(summary.overallPerformanceScore || 0).toFixed(1)}%. Focus next on engagement, fluency, and answer relevance to improve interview readiness faster.`;

  return (
    <main className={styles.dashboardShell}>
      <header className={styles.headerRow}>
        <div>
          <p className={styles.tag}>Interview Session Dashboard</p>
          <h1>{sessionMeta.jobRole} Analytics Overview</h1>
          <p className={styles.metaText}>
            Session ID: {sessionMeta.sessionId} | Domain: {sessionMeta.domain} | Date/Time: {new Date(sessionMeta.dateTime).toLocaleString()}
          </p>
        </div>
        <div className={styles.headerActions}>
          <ReportGenerator
            sessionId={sessionId}
            snapshotTargets={REPORT_CHART_SELECTORS}
            apiBaseUrl={API_BASE_URL}
          />
          <div className={styles.quickLinks}>
            <Link className={styles.quickLink} to={`/reflective/${sessionId}`}>
              Reflective Panel
            </Link>
            {sessionUserId ? (
              <Link className={styles.quickLink} to={`/progress/${sessionUserId}`}>
                Progress Trend
              </Link>
            ) : null}
          </div>
          <Link className={styles.backLink} to="/app">
            Back
          </Link>
        </div>
      </header>

      <section className={styles.scoreGrid}>
        <ScoreCard title="Engagement Score" score={summary.engagementScore} subtitle="Video + interaction consistency" icon="E" />
        <ScoreCard title="Confidence Score" score={summary.confidenceScore} subtitle="Eye contact + posture + sentiment" icon="C" />
        <ScoreCard title="Speech Fluency" score={summary.speechFluency} subtitle="Pacing, pause control, delivery" icon="S" />
        <ScoreCard title="Emotional Stability" score={summary.emotionalStability} subtitle="Emotion variance across timeline" icon="M" />
      </section>

      <section className={styles.takeawaysSection}>
        <h2>Top 3 Takeaways</h2>
        <ul>
          {topTakeaways.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <section className={styles.filterBar}>
        <strong>Modalities</strong>
        <label>
          <input type="checkbox" checked={showVideo} onChange={(event) => setShowVideo(event.target.checked)} /> Video
        </label>
        <label>
          <input type="checkbox" checked={showAudio} onChange={(event) => setShowAudio(event.target.checked)} /> Audio
        </label>
        <label>
          <input type="checkbox" checked={showFused} onChange={(event) => setShowFused(event.target.checked)} /> Combined Fused
        </label>
      </section>

      <section className={styles.videoPanel}>
        <div>
          <h3>Timeline Playback</h3>
          <p>Selected timestamp: {Number(selectedTimestamp || 0).toFixed(2)}s</p>
        </div>
        <div className={styles.videoActions}>
          <button type="button" onClick={playSelectedTimestamp} disabled={!videoUrl}>
            Play Selected Time
          </button>
        </div>
      </section>

      {videoFetchError ? <p className={styles.videoNote}>{videoFetchError}</p> : null}

      {videoUrl ? (
        <video ref={videoRef} controls className={styles.videoPlayer} src={videoUrl} />
      ) : (
        <p className={styles.videoNote}>
          Video replay is enabled when a playable URL is available. Run analysis with interview recording upload first.
        </p>
      )}

      <section className={styles.chartsSection}>
        <p className={styles.chartHint}>
          Interactive view: hover any graph for exact values, click a point to set playback time, and use answer timeline replay below.
        </p>
        {showVideo ? (
          <>
            <div data-report-chart="emotionTimeline">
              <div className={styles.chartHeaderRow}>
                <h2>Emotion Intensity by Time</h2>
                <EmotionLegend />
              </div>
              <TimelineChart
                title="Emotion Intensity by Category"
                data={chartData.emotionTimeline}
                lines={Object.entries(EMOTION_COLORS).map(([key, color]) => ({
                  key,
                  label: key,
                  color,
                }))}
                onPointSelect={(point) => setSelectedTimestamp(point.timestamp)}
              />
            </div>
            <div data-report-chart="gazeHeadPoseTimeline">
              <TimelineChart
                title="Gaze and Head Pose"
                data={chartData.gazeTimeline}
                lines={[
                  { key: "headYaw", label: "Head Yaw", color: "#0f766e" },
                  { key: "headPitch", label: "Head Pitch", color: "#2563eb" },
                  { key: "headRoll", label: "Head Roll", color: "#f59e0b" },
                  { key: "eyeContact", label: "Eye Contact %", color: "#16a34a" },
                ]}
                onPointSelect={(point) => setSelectedTimestamp(point.timestamp)}
              />
            </div>
          </>
        ) : null}

        {showAudio ? (
          <div data-report-chart="speechTimeline">
            <TimelineChart
              title="Speech Fluency and Pitch"
              data={chartData.speechTimeline}
              lines={[
                { key: "speakingRate", label: "Speaking Rate (WPM)", color: "#0284c7" },
                { key: "pitch", label: "Pitch", color: "#f97316" },
                { key: "pauseDuration", label: "Pause Duration", color: "#334155" },
                { key: "fluency", label: "Fluency %", color: "#16a34a" },
              ]}
              onPointSelect={(point) => setSelectedTimestamp(point.timestamp)}
            />
          </div>
        ) : null}

        {showFused ? (
          <div data-report-chart="engagementTimeline">
            <TimelineChart
              title="Engagement and Confidence Timeline"
              data={chartData.engagementTimeline}
              lines={[
                { key: "engagement", label: "Engagement %", color: "#0f766e" },
                { key: "confidence", label: "Confidence %", color: "#7c3aed" },
              ]}
              onPointSelect={(point) => setSelectedTimestamp(point.timestamp)}
            />
          </div>
        ) : null}
      </section>

      <section className={styles.timelineSection}>
        <h2>Answer Timeline</h2>
        <p className={styles.chartHint}>
          Hover over an answer segment to inspect timestamps, mistakes, and improvement actions for that specific answer.
        </p>
        <div className={styles.answerTimelineLayout}>
          <div className={styles.timelineRail}>
            {segmentInsightsWithContext.map((segment) => {
              const isActive = activeSegment?.segmentId === segment.segmentId;
              return (
                <button
                  key={`${segment.segmentId}-timeline`}
                  type="button"
                  className={`${styles.timelineItem} ${isActive ? styles.timelineItemActive : ""}`}
                  title={`${segment.label}: ${segment.startTime.toFixed(1)}s - ${segment.endTime.toFixed(1)}s`}
                  onMouseEnter={() => setActiveSegmentId(segment.segmentId)}
                  onFocus={() => setActiveSegmentId(segment.segmentId)}
                  onClick={() => {
                    replaySegment(segment.startTime, segment.endTime, segment.segmentId);
                  }}
                >
                  <strong>{segment.answerLabel}</strong>
                  <span>
                    {segment.startTime.toFixed(1)}s - {segment.endTime.toFixed(1)}s
                  </span>
                  {segment.questionText ? <span className={styles.timelineQuestionText}>{segment.questionText}</span> : null}
                  <span className={styles.timelineMetrics}>
                    E {segment.engagementScore.toFixed(0)} | F {segment.speechFluency.toFixed(0)} | R {segment.textRelevanceScore.toFixed(0)}
                  </span>
                  <small>{segment.recommendation}</small>
                </button>
              );
            })}
          </div>
          <aside className={styles.segmentInsightCard}>
            {activeSegment ? (
              <>
                <h3>{activeSegment.answerLabel}</h3>
                <p className={styles.metaText}>
                  {activeSegment.startTime.toFixed(1)}s - {activeSegment.endTime.toFixed(1)}s
                </p>
                {activeSegment.questionText ? <p className={styles.timelineQuestionText}>{activeSegment.questionText}</p> : null}
                <p className={styles.summaryLead}>Mistakes observed</p>
                <ul className={styles.insightList}>
                  {activeSegment.feedback.mistakes.map((item) => (
                    <li key={`mistake-${activeSegment.segmentId}-${item}`}>{item}</li>
                  ))}
                </ul>
                <p className={styles.summaryLead}>Improvements for next attempt</p>
                <ul className={styles.insightList}>
                  {activeSegment.feedback.improvements.map((item) => (
                    <li key={`improvement-${activeSegment.segmentId}-${item}`}>{item}</li>
                  ))}
                </ul>
              </>
            ) : (
              <p className={styles.metaText}>No answer segments found.</p>
            )}
          </aside>
        </div>
      </section>

      <section className={styles.answerCoachSection}>
        <h2>Answer-by-Answer Coach</h2>
        {segmentInsightsWithContext.length ? (
          <div className={styles.answerCoachGrid}>
            {segmentInsightsWithContext.map((segment) => (
              <article key={`coach-${segment.segmentId}`} className={styles.answerCoachCard}>
                <div className={styles.answerCoachHeader}>
                  <h3>{segment.answerLabel}</h3>
                  <span>
                    {segment.startTime.toFixed(1)}s - {segment.endTime.toFixed(1)}s
                  </span>
                </div>
                {segment.questionText ? <p className={styles.answerPrompt}>Question: {segment.questionText}</p> : null}
                <p className={styles.summaryLead}>What went well</p>
                <ul className={styles.insightList}>
                  {segment.coaching.strengths.map((item) => (
                    <li key={`good-${segment.segmentId}-${item}`}>{item}</li>
                  ))}
                </ul>
                <p className={styles.summaryLead}>What hurt performance</p>
                <ul className={styles.insightList}>
                  {segment.coaching.hurts.map((item) => (
                    <li key={`hurt-${segment.segmentId}-${item}`}>{item}</li>
                  ))}
                </ul>
                <p className={styles.rewriteLine}>{segment.coaching.rewriteLine}</p>
                <div className={styles.answerCoachActions}>
                  <button
                    type="button"
                    onClick={() => replaySegment(segment.startTime, segment.endTime, segment.segmentId)}
                    disabled={!videoUrl}
                  >
                    Practice This Answer Again
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className={styles.metaText}>No answer segments available for coaching cards.</p>
        )}
      </section>

      <section className={styles.evidenceSection}>
        <h2>Clip Evidence (Timestamped)</h2>
        <p className={styles.chartHint}>
          These short clips highlight where performance dropped. Use each clip to focus correction on the exact moment.
        </p>
        {evidenceClips.length ? (
          <div className={styles.evidenceGrid}>
            {evidenceClips.map((clip) => (
              <article key={`clip-${clip.segmentId}`} className={styles.evidenceCard}>
                <h3>{clip.answerLabel}</h3>
                <p className={styles.metaText}>
                  {clip.clipStart.toFixed(1)}s - {clip.clipEnd.toFixed(1)}s
                </p>
                <p>{clip.issue}</p>
                <button type="button" onClick={() => replaySegment(clip.clipStart, clip.clipEnd, clip.segmentId)} disabled={!videoUrl}>
                  Play Evidence Clip
                </button>
              </article>
            ))}
          </div>
        ) : (
          <p className={styles.metaText}>No weak evidence clips detected in available segments.</p>
        )}
      </section>

      <section className={styles.segmentSection}>
        <h2>Per-Segment Metrics</h2>
        <div className={styles.segmentGrid}>
          {segmentLabels.map((segment) => (
            <SegmentCard
              key={segment.segmentId}
              segment={segment}
              onReplay={(start, end) => replaySegment(start, end, segment.segmentId)}
            />
          ))}
        </div>
      </section>

      <section className={styles.feedbackSection}>
        <h2>Feedback Summary</h2>
        <div className={styles.feedbackGrid}>
          <article>
            <h3>Top 3 Strengths</h3>
            <ul>
              {feedbackSummary.strengths.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </article>
          <article>
            <h3>Top 3 Areas to Improve</h3>
            <ul>
              {feedbackSummary.improvements.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </article>
        </div>
        <p className={styles.feedbackText}>{feedbackSummary.suggestedFeedbackText}</p>
      </section>

      {advancedInsights ? (
        <section className={styles.advancedSection}>
          <h2>Advanced Scoring Explainability</h2>
          <p className={styles.metaText}>
            Generated: {new Date(advancedInsights.generatedAt).toLocaleString()}
          </p>
          <div className={styles.advancedScoreGrid}>
            {Object.entries(advancedInsights.numericScores || {}).map(([key, value]) => (
              <article key={key} className={styles.advancedScoreCard}>
                <h3>{key}</h3>
                <strong>{Number(value).toFixed(1)}</strong>
              </article>
            ))}
          </div>
          <div className={styles.explanationList}>
            {(advancedInsights.textualExplanations || []).map((item) => (
              <article key={item.scoreKey} className={styles.explanationItem}>
                <h3>{item.scoreKey}</h3>
                <p>{item.explanation}</p>
              </article>
            ))}
          </div>
          <div className={styles.fairnessPanel}>
            <h3>Fairness Summary</h3>
            <p>Samples audited: {advancedInsights.fairnessReport?.sampleCount ?? 0}</p>
            {(advancedInsights.fairnessReport?.warnings || []).length ? (
              <ul>
                {advancedInsights.fairnessReport.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            ) : (
              <p>No fairness warnings for current neutral feature ranges.</p>
            )}
          </div>
        </section>
      ) : null}

      <section className={styles.summarySection}>
        <h2>Self-Improvement Summary</h2>
        <p className={styles.summaryLead}>{summaryNarrative}</p>
        <div className={styles.summaryGrid}>
          <article>
            <h3>Next Practice Priorities</h3>
            <ul>
              {improvementPlan.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </article>
          <article>
            <h3>Target Benchmarks</h3>
            <ul>
              <li>Engagement Score target: 75+</li>
              <li>Speech Fluency target: 75+</li>
              <li>Confidence Score target: 75+</li>
              <li>Text Relevance target: 80+</li>
            </ul>
          </article>
        </div>
      </section>
    </main>
  );
}

export default InterviewDashboard;
