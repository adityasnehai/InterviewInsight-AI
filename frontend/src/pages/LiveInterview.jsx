import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import styles from "./LiveInterview.module.css";

function readNumericEnv(name, fallback, { min = null, max = null, integer = false } = {}) {
  const raw = import.meta.env?.[name];
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  let value = parsed;
  if (integer) {
    value = Math.round(value);
  }
  if (Number.isFinite(min) && value < min) {
    return fallback;
  }
  if (Number.isFinite(max) && value > max) {
    return fallback;
  }
  return value;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const ENABLE_PROVIDER_AVATAR = import.meta.env.VITE_ENABLE_PROVIDER_AVATAR === "1";
const SIMLI_PLAY_REMOTE_AUDIO = import.meta.env.VITE_SIMLI_PLAY_REMOTE_AUDIO !== "0";
const ENABLE_BARGE_IN = import.meta.env.VITE_ENABLE_BARGE_IN === "1";
const AVATAR_STATUS_POLL_INTERVAL_MS = 900;
const AVATAR_STATUS_POLL_ATTEMPTS = 24;
const MIN_ANSWERS_TO_END = 2;
const AUTO_LISTEN_FALLBACK_MS = 7000;
const SILENCE_SUBMIT_MS = 2200;
const MIN_WORDS_FOR_AUTO_SUBMIT = 3;
const POST_AVATAR_LISTEN_DELAY_MS = 1400;
const AVATAR_ECHO_FILTER_WINDOW_MS = 5000;
const AVATAR_ECHO_TOKEN_OVERLAP_THRESHOLD = 0.72;
const AVATAR_PROVIDER_REQUEST_TIMEOUT_MS = 4500;
const BARGE_IN_SAMPLE_MS = readNumericEnv("VITE_BARGE_IN_SAMPLE_MS", 120, {
  min: 60,
  max: 500,
  integer: true,
});
const BARGE_IN_RMS_THRESHOLD = readNumericEnv("VITE_BARGE_IN_RMS_THRESHOLD", 0.05, {
  min: 0.015,
  max: 0.25,
});
const BARGE_IN_CONSECUTIVE_FRAMES = readNumericEnv("VITE_BARGE_IN_CONSECUTIVE_FRAMES", 7, {
  min: 2,
  max: 30,
  integer: true,
});
const BARGE_IN_DYNAMIC_MULTIPLIER = readNumericEnv("VITE_BARGE_IN_DYNAMIC_MULTIPLIER", 2.25, {
  min: 1.2,
  max: 6.0,
});
const LIVE_SESSION_STORAGE_KEY = "interviewinsight_live_session";
const OFFLINE_TRANSCRIPT_PLACEHOLDER = "[Voice response captured. Transcript unavailable.]";
const ANALYSIS_STEPS = [
  "Uploading interview recording",
  "Extracting multimodal signals",
  "Computing performance scores",
  "Preparing dashboard insights",
];
const getSpeechRecognitionClass = () => {
  if (typeof window === "undefined") {
    return null;
  }
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
};

let livekitLoaderPromise = null;

async function loadLiveKitBrowserLibrary() {
  if (typeof window === "undefined") {
    throw new Error("LiveKit is only available in browser runtime.");
  }
  if (window.LivekitClient) {
    return window.LivekitClient;
  }
  if (!livekitLoaderPromise) {
    livekitLoaderPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://unpkg.com/livekit-client/dist/livekit-client.umd.js";
      script.async = true;
      script.onload = () => {
        if (window.LivekitClient) {
          resolve(window.LivekitClient);
        } else {
          reject(new Error("LiveKit library loaded but global object is missing."));
        }
      };
      script.onerror = () => reject(new Error("Failed to load LiveKit browser library."));
      document.head.appendChild(script);
    });
  }
  return livekitLoaderPromise;
}

function resolveProviderVideoUrl(payload) {
  const directUrl = String(payload?.videoUrl || "").trim();
  if (directUrl) {
    return directUrl;
  }

  const providerPayload = payload?.providerPayload;
  if (!providerPayload || typeof providerPayload !== "object") {
    return "";
  }

  const stack = [providerPayload];
  while (stack.length > 0) {
    const current = stack.pop();
    if (!current || typeof current !== "object") {
      continue;
    }
    const keys = ["videoUrl", "video_url", "streamUrl", "stream_url", "hlsUrl", "hls_url", "url"];
    for (const key of keys) {
      const value = current[key];
      if (typeof value === "string" && /^https?:\/\//i.test(value)) {
        return value;
      }
    }
    for (const value of Object.values(current)) {
      if (value && typeof value === "object") {
        stack.push(value);
      }
    }
  }

  return "";
}

function formatDuration(totalSeconds) {
  const safe = Math.max(0, Number(totalSeconds || 0));
  const mins = Math.floor(safe / 60);
  const secs = safe % 60;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function normalizeAnswer(value) {
  return String(value || "")
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
}

function countWords(value) {
  const cleaned = String(value || "")
    .trim()
    .replace(/\s+/g, " ");
  if (!cleaned) {
    return 0;
  }
  return cleaned.split(" ").length;
}

function appendUniqueText(baseText, nextText) {
  const base = String(baseText || "").trim();
  const next = String(nextText || "").trim();
  if (!next) {
    return base;
  }
  if (!base) {
    return next;
  }
  if (base.endsWith(next)) {
    return base;
  }
  if (next.endsWith(base)) {
    return next;
  }
  const overlapWindow = Math.min(80, base.length, next.length);
  for (let size = overlapWindow; size >= 8; size -= 1) {
    if (base.slice(-size).toLowerCase() === next.slice(0, size).toLowerCase()) {
      return `${base} ${next.slice(size).trim()}`.trim();
    }
  }
  return `${base} ${next}`.trim();
}

function normalizeSpeechText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function tokenOverlapRatio(candidateText, referenceText) {
  const candidateTokens = new Set(normalizeSpeechText(candidateText).split(" ").filter(Boolean));
  const referenceTokens = new Set(normalizeSpeechText(referenceText).split(" ").filter(Boolean));
  if (candidateTokens.size === 0 || referenceTokens.size === 0) {
    return 0;
  }
  let overlap = 0;
  for (const token of candidateTokens) {
    if (referenceTokens.has(token)) {
      overlap += 1;
    }
  }
  return overlap / candidateTokens.size;
}

function isLikelyAvatarEcho(candidateText, questionText, listenAgeMs) {
  if (listenAgeMs > AVATAR_ECHO_FILTER_WINDOW_MS) {
    return false;
  }
  const candidateWords = countWords(candidateText);
  const questionWords = countWords(questionText);
  if (candidateWords === 0 || questionWords === 0) {
    return false;
  }
  const overlap = tokenOverlapRatio(candidateText, questionText);
  return overlap >= AVATAR_ECHO_TOKEN_OVERLAP_THRESHOLD && candidateWords <= Math.max(28, questionWords + 6);
}

function stripLeadingQuestionEcho(candidateText, questionText) {
  const raw = String(candidateText || "").trim().replace(/\s+/g, " ");
  const question = String(questionText || "").trim().replace(/\s+/g, " ");
  if (!raw || !question) {
    return raw;
  }

  const rawTokens = raw.split(" ");
  const tokenPairs = rawTokens
    .map((token, idx) => ({
      rawIndex: idx,
      norm: token.toLowerCase().replace(/[^a-z0-9]/g, ""),
    }))
    .filter((item) => item.norm);
  const questionTokens = normalizeSpeechText(question).split(" ").filter(Boolean);
  if (tokenPairs.length === 0 || questionTokens.length < 5) {
    return raw;
  }

  const limit = Math.min(tokenPairs.length, questionTokens.length);
  let commonPrefix = 0;
  for (let i = 0; i < limit; i += 1) {
    if (tokenPairs[i].norm !== questionTokens[i]) {
      break;
    }
    commonPrefix += 1;
  }

  const minPrefixForStrip = Math.max(4, Math.floor(questionTokens.length * 0.55));
  if (commonPrefix >= minPrefixForStrip) {
    const dropRawIndex = tokenPairs[commonPrefix - 1]?.rawIndex ?? -1;
    return rawTokens.slice(dropRawIndex + 1).join(" ").trim();
  }

  const compareCount = Math.min(tokenPairs.length, questionTokens.length + 6);
  const candidatePrefix = tokenPairs.slice(0, compareCount).map((item) => item.norm);
  const questionSet = new Set(questionTokens);
  const overlap = candidatePrefix.reduce((acc, token) => acc + (questionSet.has(token) ? 1 : 0), 0);
  const overlapRatio = compareCount > 0 ? overlap / compareCount : 0;
  const startsSame = candidatePrefix[0] && candidatePrefix[0] === questionTokens[0];

  if (startsSame && overlapRatio >= 0.78) {
    const removePairs = Math.min(tokenPairs.length, questionTokens.length);
    const dropRawIndex = tokenPairs[removePairs - 1]?.rawIndex ?? -1;
    return rawTokens.slice(dropRawIndex + 1).join(" ").trim();
  }

  return raw;
}

function mapLiveTurns(rawTurns) {
  if (!Array.isArray(rawTurns)) {
    return [];
  }
  return rawTurns
    .map((turn) => ({
      role: String(turn?.role || "").toLowerCase() === "assistant" ? "assistant" : "user",
      text: String(turn?.text || "").trim(),
    }))
    .filter((turn) => turn.text);
}

function makeIsoNow() {
  return new Date().toISOString();
}

function loadStoredLiveSession() {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(LIVE_SESSION_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || !parsed.sessionId) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function LiveInterview() {
  const navigate = useNavigate();
  const { token, logout } = useAuth();
  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const [jobRole, setJobRole] = useState("Backend Engineer");
  const [domain, setDomain] = useState("FinTech");
  const [sessionId, setSessionId] = useState("");
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [answerText, setAnswerText] = useState("");
  const [latestTranscript, setLatestTranscript] = useState("");
  const [committedTranscript, setCommittedTranscript] = useState("");
  const [interimTranscript, setInterimTranscript] = useState("");
  const [turns, setTurns] = useState([]);
  const [timelineMarkers, setTimelineMarkers] = useState([]);
  const [listening, setListening] = useState(false);
  const [recognitionText, setRecognitionText] = useState("");
  const [sttFallbackMode, setSttFallbackMode] = useState(false);
  const [sttFallbackReason, setSttFallbackReason] = useState("");
  const [avatarSpeaking, setAvatarSpeaking] = useState(false);
  const [avatarProviderEnabled, setAvatarProviderEnabled] = useState(false);
  const [avatarProviderName, setAvatarProviderName] = useState("browser");
  const [avatarProviderStatus, setAvatarProviderStatus] = useState("");
  const [avatarRenderStatus, setAvatarRenderStatus] = useState("idle");
  const [avatarVideoUrl, setAvatarVideoUrl] = useState("");
  const [simliConnecting, setSimliConnecting] = useState(false);
  const [simliConnected, setSimliConnected] = useState(false);
  const [simliError, setSimliError] = useState("");

  const [starting, setStarting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [ending, setEnding] = useState(false);
  const [recording, setRecording] = useState(false);
  const [interviewComplete, setInterviewComplete] = useState(false);
  const [sessionStartTs, setSessionStartTs] = useState(null);
  const [pausedAtTs, setPausedAtTs] = useState(null);
  const [pausedAccumulatedMs, setPausedAccumulatedMs] = useState(0);
  const [interviewPaused, setInterviewPaused] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [analysisStepIndex, setAnalysisStepIndex] = useState(0);
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [recoveryMessage, setRecoveryMessage] = useState("");
  const [deviceCheckRunning, setDeviceCheckRunning] = useState(false);
  const [deviceCheck, setDeviceCheck] = useState({
    checked: false,
    camera: false,
    microphone: false,
    speaker: false,
    network: false,
    details: "",
  });
  const [error, setError] = useState("");

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const recognitionRef = useRef(null);
  const recognitionStartingRef = useRef(false);
  const pendingVoiceSubmitRef = useRef("");
  const forceSubmitOnStopRef = useRef(false);
  const silenceSubmitTimerRef = useRef(null);
  const autoListenTimerRef = useRef(null);
  const shouldAutoListenRef = useRef(false);
  const autoCaptureActiveRef = useRef(false);
  const avatarHeardSpeakingRef = useRef(false);
  const avatarAudioRef = useRef(null);
  const avatarVideoRef = useRef(null);
  const avatarPollTokenRef = useRef(0);
  const avatarSpeakTokenRef = useRef(0);
  const avatarSpeakingTimeoutRef = useRef(null);
  const lastSpokenQuestionRef = useRef("");
  const submitInFlightRef = useRef(false);
  const lastSubmittedNormalizedRef = useRef("");
  const lastSubmittedAtRef = useRef(0);
  const answerTextRef = useRef("");
  const latestTranscriptRef = useRef("");
  const transcriptFinalRef = useRef("");
  const transcriptInterimRef = useRef("");
  const currentQuestionRef = useRef("");
  const avatarSpeakingRef = useRef(false);
  const avatarSpeechEndedAtRef = useRef(0);
  const listeningStartedAtRef = useRef(0);
  const lastSpeechDetectedAtRef = useRef(0);
  const pendingTranscriptConfidenceRef = useRef(0.75);
  const turnEvalInFlightRef = useRef(false);
  const questionAskedAtRef = useRef("");
  const answerStartedAtRef = useRef("");
  const sessionIdRef = useRef("");
  const submittingRef = useRef(false);
  const endingRef = useRef(false);
  const interviewPausedRef = useRef(false);
  const interviewCompleteRef = useRef(false);
  const simliRoomRef = useRef(null);
  const simliVideoRef = useRef(null);
  const simliMicTrackRef = useRef(null);
  const simliConnectStartedAtRef = useRef(0);
  const simliTrackIdsRef = useRef(new Set());
  const simliAudioElsRef = useRef([]);
  const micAudioContextRef = useRef(null);
  const bargeInIntervalRef = useRef(null);
  const bargeInStreakRef = useRef(0);
  const bargeInNoiseFloorRef = useRef(0.012);

  const sttAvailable = Boolean(getSpeechRecognitionClass());

  useEffect(() => {
    answerTextRef.current = answerText;
  }, [answerText]);

  useEffect(() => {
    latestTranscriptRef.current = latestTranscript;
  }, [latestTranscript]);

  useEffect(() => {
    currentQuestionRef.current = currentQuestion;
  }, [currentQuestion]);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    submittingRef.current = submitting;
  }, [submitting]);

  useEffect(() => {
    endingRef.current = ending;
  }, [ending]);

  useEffect(() => {
    interviewPausedRef.current = interviewPaused;
  }, [interviewPaused]);

  useEffect(() => {
    interviewCompleteRef.current = interviewComplete;
  }, [interviewComplete]);

  useEffect(() => {
    avatarSpeakingRef.current = avatarSpeaking;
    if (!avatarSpeaking) {
      avatarSpeechEndedAtRef.current = Date.now();
      bargeInStreakRef.current = 0;
    }
  }, [avatarSpeaking]);

  useEffect(() => {
    if (!sessionId) {
      if (typeof window !== "undefined") {
        window.localStorage.removeItem(LIVE_SESSION_STORAGE_KEY);
      }
      return;
    }
    if (typeof window === "undefined") {
      return;
    }
    const snapshot = {
      sessionId,
      jobRole,
      domain,
      interviewPaused,
      sessionStartTs,
      pausedAtTs,
      pausedAccumulatedMs,
      elapsedSeconds,
    };
    window.localStorage.setItem(LIVE_SESSION_STORAGE_KEY, JSON.stringify(snapshot));
  }, [sessionId, jobRole, domain, interviewPaused, sessionStartTs, pausedAtTs, pausedAccumulatedMs, elapsedSeconds]);

  useEffect(() => {
    return () => {
      if (autoListenTimerRef.current) {
        window.clearTimeout(autoListenTimerRef.current);
        autoListenTimerRef.current = null;
      }
      stopListening();
      recognitionStartingRef.current = false;
      stopAvatarSpeech();
      disconnectSimliRoom();
      stopBargeInMonitor();
      stopMediaResources();
      if (avatarSpeakingTimeoutRef.current) {
        window.clearTimeout(avatarSpeakingTimeoutRef.current);
        avatarSpeakingTimeoutRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!token || sessionId) {
      return;
    }
    const stored = loadStoredLiveSession();
    if (!stored?.sessionId) {
      return;
    }
    void restoreLiveSession(stored);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, sessionId]);

  useEffect(() => {
    let mounted = true;

    async function loadAvatarConfig() {
      if (!ENABLE_PROVIDER_AVATAR) {
        if (!mounted) {
          return;
        }
        setAvatarProviderEnabled(false);
        setAvatarProviderName("browser");
        setAvatarProviderStatus("Provider avatar feature flag disabled. Using browser TTS.");
        setAvatarVideoUrl("");
        return;
      }

      try {
        const response = await fetch(`${API_BASE_URL}/app/live/avatar/config`, {
          headers: authHeaders,
        });
        if (response.status === 401) {
          throw new Error("Your login session expired. Please sign in again.");
        }
        if (!response.ok) {
          throw new Error(`Unable to load avatar config (${response.status})`);
        }
        const payload = await response.json();
        if (!mounted) {
          return;
        }
        setAvatarProviderEnabled(Boolean(payload.enabled));
        setAvatarProviderName(payload.provider || "browser");
        setAvatarProviderStatus(payload.message || "");
        if (!payload.enabled) {
          setAvatarVideoUrl("");
        }
      } catch (err) {
        if (!mounted) {
          return;
        }
        if (String(err.message || "").toLowerCase().includes("expired")) {
          logout();
          navigate("/auth", { replace: true });
          return;
        }
        setAvatarProviderEnabled(false);
        setAvatarProviderName("browser");
        setAvatarProviderStatus("Provider avatar unavailable. Using browser TTS.");
        setAvatarVideoUrl("");
      }
    }

    loadAvatarConfig();
    return () => {
      mounted = false;
    };
  }, [authHeaders, logout, navigate]);

  useEffect(() => {
    if (!avatarVideoRef.current || !avatarVideoUrl) {
      return;
    }
    const video = avatarVideoRef.current;
    const playPromise = video.play();
    if (playPromise && typeof playPromise.catch === "function") {
      playPromise.catch(() => {
        // Browser autoplay may be blocked; controls remain available for manual play.
      });
    }
  }, [avatarVideoUrl]);

  useEffect(() => {
    if (!currentQuestion || !sessionId || interviewComplete || interviewPaused) {
      return;
    }
    if (currentQuestion === lastSpokenQuestionRef.current) {
      return;
    }
    questionAskedAtRef.current = makeIsoNow();
    answerStartedAtRef.current = "";
    primeAutoListeningWindow();
    lastSpokenQuestionRef.current = currentQuestion;
    void speakWithAvatar(currentQuestion);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentQuestion, sessionId, interviewComplete, interviewPaused]);

  useEffect(() => {
    if (!shouldAutoListenRef.current || interviewPaused) {
      return;
    }
    if (avatarSpeaking) {
      avatarHeardSpeakingRef.current = true;
      return;
    }
    if (!avatarHeardSpeakingRef.current || listening || submitting || ending || interviewComplete || interviewPaused) {
      return;
    }
    if (autoListenTimerRef.current) {
      window.clearTimeout(autoListenTimerRef.current);
      autoListenTimerRef.current = null;
    }
    const started = startListening({ interruptAvatar: false });
    if (started) {
      shouldAutoListenRef.current = false;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [avatarSpeaking, listening, submitting, ending, interviewComplete, interviewPaused]);

  useEffect(() => {
    if (!sessionId || !avatarProviderEnabled || avatarProviderName !== "simli") {
      disconnectSimliRoom();
      return;
    }
    void connectSimliRoom(sessionId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, avatarProviderEnabled, avatarProviderName]);

  useEffect(() => {
    if (!sessionId || !avatarProviderEnabled || avatarProviderName !== "simli" || simliConnected || simliConnecting) {
      return;
    }
    const startedAt = simliConnectStartedAtRef.current;
    if (startedAt > 0 && Date.now() - startedAt > 20000) {
      setSimliError("Avatar stream not connected. Simli may be rate-limited (429). Wait ~1 minute and retry.");
      setAvatarProviderStatus("Simli stream unavailable or rate-limited. Verify worker and LiveKit credentials.");
    }
    const retryId = window.setTimeout(() => {
      void connectSimliRoom(sessionId);
    }, 4000);
    return () => {
      window.clearTimeout(retryId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, avatarProviderEnabled, avatarProviderName, simliConnected, simliConnecting]);

  useEffect(() => {
    if (!sessionStartTs || ending) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      const pausedNow = interviewPaused && pausedAtTs ? Date.now() - pausedAtTs : 0;
      const elapsedMs = Date.now() - sessionStartTs - pausedAccumulatedMs - pausedNow;
      setElapsedSeconds(Math.max(0, Math.floor(elapsedMs / 1000)));
    }, 1000);
    return () => {
      window.clearInterval(timer);
    };
  }, [sessionStartTs, ending, interviewPaused, pausedAtTs, pausedAccumulatedMs]);

  useEffect(() => {
    if (!sessionId || ending) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      void syncLiveState(sessionId);
    }, 10000);
    return () => {
      window.clearInterval(intervalId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, ending]);

  useEffect(() => {
    if (!ending) {
      setAnalysisStepIndex(0);
      setAnalysisProgress(0);
      return undefined;
    }
    const ticker = window.setInterval(() => {
      setAnalysisProgress((prev) => Math.min(prev + 1.5, 92));
    }, 420);
    return () => {
      window.clearInterval(ticker);
    };
  }, [ending]);

  useEffect(() => {
    if (!ending) {
      return;
    }
    if (analysisProgress < 24) {
      setAnalysisStepIndex(0);
      return;
    }
    if (analysisProgress < 52) {
      setAnalysisStepIndex(1);
      return;
    }
    if (analysisProgress < 78) {
      setAnalysisStepIndex(2);
      return;
    }
    setAnalysisStepIndex(3);
  }, [analysisProgress, ending]);

  const answeredCount = useMemo(
    () => turns.filter((item) => String(item?.role || "") === "user").length,
    [turns]
  );
  const liveTranscript = String(
    recognitionText || `${committedTranscript} ${interimTranscript}` || answerText || latestTranscript || ""
  ).trim();
  const turnState = useMemo(() => {
    if (interviewPaused) {
      return "Paused";
    }
    if (ending || submitting) {
      return "Processing";
    }
    if (avatarSpeaking) {
      return "AI Speaking";
    }
    if (listening) {
      return "Listening";
    }
    return "Ready";
  }, [interviewPaused, ending, submitting, avatarSpeaking, listening]);
  const speechCaptureUnavailable = !sttAvailable || sttFallbackMode;
  const canEndInterview =
    interviewComplete ||
    answeredCount >= MIN_ANSWERS_TO_END ||
    countWords(liveTranscript) >= MIN_WORDS_FOR_AUTO_SUBMIT;

  function primeAutoListeningWindow() {
    shouldAutoListenRef.current = true;
    autoCaptureActiveRef.current = true;
    avatarHeardSpeakingRef.current = false;
    if (autoListenTimerRef.current) {
      window.clearTimeout(autoListenTimerRef.current);
      autoListenTimerRef.current = null;
    }
    autoListenTimerRef.current = window.setTimeout(() => {
      if (!shouldAutoListenRef.current || listening || submitting || ending || interviewComplete || interviewPaused) {
        return;
      }
      if (avatarSpeakingRef.current) {
        autoListenTimerRef.current = window.setTimeout(() => {
          if (!shouldAutoListenRef.current || listening || submitting || ending || interviewComplete || interviewPaused) {
            return;
          }
          const started = startListening({ interruptAvatar: false });
          if (started) {
            shouldAutoListenRef.current = false;
          }
        }, 900);
        return;
      }
      const started = startListening({ interruptAvatar: false });
      if (started) {
        shouldAutoListenRef.current = false;
      }
    }, AUTO_LISTEN_FALLBACK_MS);
  }

  function clearTranscriptDrafts() {
    setRecognitionText("");
    setAnswerText("");
    setLatestTranscript("");
    setCommittedTranscript("");
    setInterimTranscript("");
    transcriptFinalRef.current = "";
    transcriptInterimRef.current = "";
    pendingVoiceSubmitRef.current = "";
  }

  async function evaluateTurnServerSide(transcript, options = {}) {
    const text = String(transcript || "").trim();
    const words = countWords(text);
    if (!text || !sessionIdRef.current) {
      return {
        shouldSubmit: words >= MIN_WORDS_FOR_AUTO_SUBMIT,
        shouldKeepListening: words < MIN_WORDS_FOR_AUTO_SUBMIT,
        action: words >= MIN_WORDS_FOR_AUTO_SUBMIT ? "submit" : "keep_listening",
        confidenceHint: words >= MIN_WORDS_FOR_AUTO_SUBMIT ? 0.7 : 0.0,
      };
    }
    if (turnEvalInFlightRef.current) {
      return null;
    }
    turnEvalInFlightRef.current = true;
    try {
      const response = await fetch(`${API_BASE_URL}/app/live/${sessionIdRef.current}/turn-evaluate`, {
        method: "POST",
        headers: {
          ...authHeaders,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          transcript: text,
          listeningMs: Number(options.listeningMs || 0),
          silenceMs: Number(options.silenceMs || 0),
          isFinal: Boolean(options.isFinal),
          minWords: MIN_WORDS_FOR_AUTO_SUBMIT,
        }),
      });
      if (response.status === 401) {
        throw new Error("Your login session expired. Please sign in again.");
      }
      if (!response.ok) {
        return null;
      }
      return await response.json();
    } catch (err) {
      if (String(err.message || "").toLowerCase().includes("expired")) {
        logout();
        navigate("/auth", { replace: true });
        return null;
      }
      return null;
    } finally {
      turnEvalInFlightRef.current = false;
    }
  }

  async function maybeSubmitTranscript(finalText, options = {}) {
    const rawText = String(finalText || "").trim();
    const text = stripLeadingQuestionEcho(rawText, currentQuestionRef.current);
    if (!text) {
      return false;
    }
    const listeningMs =
      Number(options.listeningMs || 0) || Math.max(0, Date.now() - Number(listeningStartedAtRef.current || 0));
    const silenceMs =
      Number(options.silenceMs || 0) || Math.max(0, Date.now() - Number(lastSpeechDetectedAtRef.current || 0));
    const decision = await evaluateTurnServerSide(text, {
      listeningMs,
      silenceMs,
      isFinal: Boolean(options.isFinal),
    });

    if (decision?.action === "ignore_echo") {
      clearTranscriptDrafts();
      return false;
    }

    const localFallbackSubmit =
      countWords(text) >= MIN_WORDS_FOR_AUTO_SUBMIT && (Boolean(options.forceSubmit) || Boolean(options.isFinal));
    const shouldSubmit = Boolean(decision?.shouldSubmit) || (!decision && localFallbackSubmit) || (Boolean(options.forceSubmit) && localFallbackSubmit);
    if (!shouldSubmit) {
      return false;
    }
    const answerEndedAt = makeIsoNow();
    const confidenceHint =
      typeof decision?.confidenceHint === "number" ? Number(decision.confidenceHint) : pendingTranscriptConfidenceRef.current;
    pendingTranscriptConfidenceRef.current = Math.max(0.0, Math.min(1.0, confidenceHint));
    return await submitAnswerText(text, {
      questionAskedAt: questionAskedAtRef.current || null,
      answerStartedAt: answerStartedAtRef.current || answerEndedAt,
      answerEndedAt,
      transcriptConfidence: pendingTranscriptConfidenceRef.current,
    });
  }

  function startBargeInMonitor(stream) {
    if (!ENABLE_BARGE_IN) {
      return;
    }
    stopBargeInMonitor();
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass || !stream) {
      return;
    }
    try {
      const ctx = new AudioContextClass();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      analyser.smoothingTimeConstant = 0.85;
      source.connect(analyser);
      const data = new Uint8Array(analyser.fftSize);
      bargeInNoiseFloorRef.current = 0.012;
      micAudioContextRef.current = ctx;
      bargeInIntervalRef.current = window.setInterval(() => {
        analyser.getByteTimeDomainData(data);
        let sumSquares = 0;
        for (let i = 0; i < data.length; i += 1) {
          const normalized = (data[i] - 128) / 128;
          sumSquares += normalized * normalized;
        }
        const rms = Math.sqrt(sumSquares / data.length);

        const priorNoiseFloor = bargeInNoiseFloorRef.current;
        const candidateNoise = priorNoiseFloor * 0.88 + rms * 0.12;
        bargeInNoiseFloorRef.current = Math.max(0.005, Math.min(0.14, candidateNoise));
        const dynamicThreshold = Math.max(
          BARGE_IN_RMS_THRESHOLD,
          bargeInNoiseFloorRef.current * BARGE_IN_DYNAMIC_MULTIPLIER + 0.008
        );

        if (
          !avatarSpeakingRef.current ||
          recognitionRef.current ||
          submittingRef.current ||
          endingRef.current ||
          interviewPausedRef.current ||
          interviewCompleteRef.current ||
          !sessionIdRef.current
        ) {
          bargeInStreakRef.current = 0;
          return;
        }
        if (rms >= dynamicThreshold) {
          bargeInStreakRef.current += 1;
        } else {
          bargeInStreakRef.current = 0;
        }
        if (bargeInStreakRef.current >= BARGE_IN_CONSECUTIVE_FRAMES) {
          bargeInStreakRef.current = 0;
          setAvatarProviderStatus("Interruption detected. Switching to your answer.");
          startListening({ interruptAvatar: true });
        }
      }, BARGE_IN_SAMPLE_MS);
    } catch {
      // mic monitor is best effort
    }
  }

  function stopBargeInMonitor() {
    bargeInStreakRef.current = 0;
    bargeInNoiseFloorRef.current = 0.012;
    if (bargeInIntervalRef.current) {
      window.clearInterval(bargeInIntervalRef.current);
      bargeInIntervalRef.current = null;
    }
    if (micAudioContextRef.current) {
      try {
        micAudioContextRef.current.close();
      } catch {
        // ignore cleanup failures
      }
      micAudioContextRef.current = null;
    }
  }

  function clearStoredLiveSession() {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.removeItem(LIVE_SESSION_STORAGE_KEY);
  }

  async function runDeviceCheck() {
    setDeviceCheckRunning(true);
    try {
      let network = false;
      try {
        const controller = new AbortController();
        const timeoutId = window.setTimeout(() => controller.abort(), 4000);
        const healthResp = await fetch(`${API_BASE_URL}/health`, { signal: controller.signal });
        window.clearTimeout(timeoutId);
        network = healthResp.ok;
      } catch {
        network = false;
      }

      let camera = false;
      let microphone = false;
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
        camera = stream.getVideoTracks().length > 0;
        microphone = stream.getAudioTracks().length > 0;
        stream.getTracks().forEach((track) => track.stop());
      } catch {
        camera = false;
        microphone = false;
      }

      const speaker = typeof window !== "undefined" && ("AudioContext" in window || "webkitAudioContext" in window);
      const details = [];
      if (!network) details.push("Backend unreachable");
      if (!camera) details.push("Camera unavailable");
      if (!microphone) details.push("Microphone unavailable");
      if (!speaker) details.push("Speaker check unavailable");

      const result = {
        checked: true,
        network,
        camera,
        microphone,
        speaker: Boolean(speaker),
        details: details.join(", "),
      };
      setDeviceCheck(result);
      return result;
    } finally {
      setDeviceCheckRunning(false);
    }
  }

  async function restoreLiveSession(snapshot) {
    if (!snapshot?.sessionId || sessionId) {
      return;
    }
    try {
      const response = await fetch(`${API_BASE_URL}/app/live/${snapshot.sessionId}/state`, {
        headers: authHeaders,
      });
      if (response.status === 401) {
        throw new Error("Your login session expired. Please sign in again.");
      }
      if (!response.ok) {
        clearStoredLiveSession();
        return;
      }
      const payload = await response.json();
      const complete = String(payload.status || "").toLowerCase() === "live_completed";
      if (complete) {
        clearStoredLiveSession();
        return;
      }
      setJobRole(String(snapshot.jobRole || jobRole));
      setDomain(String(snapshot.domain || domain));
      setSessionId(String(snapshot.sessionId));
      setTurns(mapLiveTurns(payload.turns));
      setCurrentQuestion(String(payload.currentQuestion || ""));
      setTimelineMarkers(Array.isArray(payload.timelineMarkers) ? payload.timelineMarkers : []);
      setInterviewComplete(false);
      setSttFallbackMode(false);
      setSttFallbackReason("");
      clearTranscriptDrafts();
      setSessionStartTs(
        Number.isFinite(Number(snapshot.sessionStartTs)) ? Number(snapshot.sessionStartTs) : Date.now()
      );
      setPausedAccumulatedMs(Math.max(0, Number(snapshot.pausedAccumulatedMs || 0)));
      if (snapshot.interviewPaused) {
        setInterviewPaused(true);
        setPausedAtTs(Number.isFinite(Number(snapshot.pausedAtTs)) ? Number(snapshot.pausedAtTs) : Date.now());
      } else {
        setInterviewPaused(false);
        setPausedAtTs(null);
      }
      setElapsedSeconds(Math.max(0, Number(snapshot.elapsedSeconds || 0)));
      setRecoveryMessage("Recovered previous live interview session.");
      await beginRecording();
      void syncLiveState(String(snapshot.sessionId));
    } catch (err) {
      if (String(err.message || "").toLowerCase().includes("expired")) {
        logout();
        navigate("/auth", { replace: true });
        return;
      }
      setError("Could not restore previous session. Start a new interview.");
      clearStoredLiveSession();
    }
  }

  function togglePauseInterview() {
    if (!sessionId || ending || interviewComplete) {
      return;
    }
    if (interviewPaused) {
      const pauseDelta = pausedAtTs ? Date.now() - pausedAtTs : 0;
      setPausedAccumulatedMs((prev) => prev + Math.max(0, pauseDelta));
      setPausedAtTs(null);
      setInterviewPaused(false);
      setRecoveryMessage("Interview resumed.");
      if (currentQuestion) {
        questionAskedAtRef.current = makeIsoNow();
        answerStartedAtRef.current = "";
        primeAutoListeningWindow();
        void speakWithAvatar(currentQuestion);
      }
      return;
    }
    setInterviewPaused(true);
    setPausedAtTs(Date.now());
    shouldAutoListenRef.current = false;
    autoCaptureActiveRef.current = false;
    if (autoListenTimerRef.current) {
      window.clearTimeout(autoListenTimerRef.current);
      autoListenTimerRef.current = null;
    }
    stopListening({ submitAfterStop: false });
    stopAvatarSpeech();
    setRecoveryMessage("Interview paused.");
  }

  function repeatCurrentQuestion() {
    if (!sessionId || !currentQuestion || ending || interviewComplete || interviewPaused) {
      return;
    }
    stopListening({ submitAfterStop: false });
    clearTranscriptDrafts();
    pendingTranscriptConfidenceRef.current = 0.75;
    questionAskedAtRef.current = makeIsoNow();
    answerStartedAtRef.current = "";
    primeAutoListeningWindow();
    void speakWithAvatar(currentQuestion);
  }

  async function skipCurrentQuestion() {
    if (!sessionId || ending || interviewComplete || interviewPaused) {
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      stopListening({ submitAfterStop: false });
      stopAvatarSpeech();
      const skippedAt = makeIsoNow();
      const response = await fetch(`${API_BASE_URL}/app/live/${sessionId}/skip`, {
        method: "POST",
        headers: {
          ...authHeaders,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          questionAskedAt: questionAskedAtRef.current || null,
          skippedAt,
        }),
      });
      if (response.status === 401) {
        throw new Error("Your login session expired. Please sign in again.");
      }
      if (!response.ok) {
        throw new Error(`Failed to skip question (${response.status})`);
      }
      const payload = await response.json();
      setTurns((prev) => [
        ...prev,
        { role: "user", text: "[Question skipped]" },
        ...(payload.nextQuestion ? [{ role: "assistant", text: payload.nextQuestion }] : []),
      ]);
      setCurrentQuestion(payload.nextQuestion || "");
      setInterviewComplete(Boolean(payload.isInterviewComplete));
      clearTranscriptDrafts();
      answerStartedAtRef.current = "";
      questionAskedAtRef.current = "";
      pendingTranscriptConfidenceRef.current = 0.75;
      void syncLiveState(sessionId);
    } catch (err) {
      if (String(err.message || "").toLowerCase().includes("expired")) {
        logout();
        navigate("/auth", { replace: true });
        return;
      }
      setError(err.message || "Unable to skip current question.");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitOfflineAnswer() {
    if (!sessionId || ending || interviewComplete || interviewPaused) {
      return;
    }
    const submittedAt = makeIsoNow();
    await submitAnswerText(`${OFFLINE_TRANSCRIPT_PLACEHOLDER} (${submittedAt})`, {
      force: true,
      questionAskedAt: questionAskedAtRef.current || null,
      answerStartedAt: answerStartedAtRef.current || submittedAt,
      answerEndedAt: submittedAt,
      transcriptConfidence: 0.0,
    });
  }

  async function syncLiveState(activeSessionId = sessionId) {
    if (!activeSessionId) {
      return;
    }
    try {
      const response = await fetch(`${API_BASE_URL}/app/live/${activeSessionId}/state`, {
        headers: authHeaders,
      });
      if (response.status === 401) {
        throw new Error("Your login session expired. Please sign in again.");
      }
      if (!response.ok) {
        return;
      }
      const payload = await response.json();
      const turnsFromState = mapLiveTurns(payload.turns);
      if (turnsFromState.length > 0) {
        setTurns(turnsFromState);
      }
      setTimelineMarkers(Array.isArray(payload.timelineMarkers) ? payload.timelineMarkers : []);
      setCurrentQuestion(String(payload.currentQuestion || ""));
      const complete = String(payload.status || "").toLowerCase() === "live_completed";
      setInterviewComplete(complete);
      if (complete) {
        autoCaptureActiveRef.current = false;
        clearStoredLiveSession();
      }
    } catch (err) {
      if (String(err.message || "").toLowerCase().includes("expired")) {
        logout();
        navigate("/auth", { replace: true });
      }
    }
  }

  async function startInterview(event) {
    event.preventDefault();
    const needsFreshCheck = !deviceCheck.checked || !deviceCheck.camera || !deviceCheck.microphone || !deviceCheck.network;
    const checked = needsFreshCheck ? await runDeviceCheck() : deviceCheck;
    const deviceReady = Boolean(checked?.camera && checked?.microphone && checked?.network);
    if (!deviceReady) {
      setError(
        "Complete device check first: camera, microphone, and backend network connection are required."
      );
      return;
    }
    setStarting(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/app/live/start`, {
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
        throw new Error("Your login session expired. Please sign in again.");
      }
      if (!response.ok) {
        throw new Error(`Unable to start live interview (${response.status})`);
      }
      const payload = await response.json();
      const fallbackGreeting = `Hi, great to meet you. To start, can you briefly introduce yourself and your experience as a ${jobRole.trim() || "professional"}?`;
      const initialQuestion = String(payload.currentQuestion || "").trim() || fallbackGreeting;
      setSessionId(payload.sessionId);
      setCurrentQuestion(initialQuestion);
      setTurns([
        {
          role: "assistant",
          text: initialQuestion,
        },
      ]);
      setSessionStartTs(Date.now());
      setPausedAtTs(null);
      setPausedAccumulatedMs(0);
      setInterviewPaused(false);
      setElapsedSeconds(0);
      setInterviewComplete(false);
      setRecoveryMessage("");
      setSttFallbackMode(false);
      setSttFallbackReason("");
      clearTranscriptDrafts();
      setTimelineMarkers([]);
      lastSubmittedNormalizedRef.current = "";
      lastSubmittedAtRef.current = 0;
      pendingTranscriptConfidenceRef.current = 0.75;
      lastSpokenQuestionRef.current = "";
      await beginRecording();
      if (
        ENABLE_PROVIDER_AVATAR &&
        avatarProviderEnabled &&
        String(avatarProviderName || "").toLowerCase() === "simli"
      ) {
        void connectSimliRoom(payload.sessionId);
      }
      void syncLiveState(payload.sessionId);
    } catch (err) {
      if (String(err.message || "").toLowerCase().includes("expired")) {
        logout();
        navigate("/auth", { replace: true });
        return;
      }
      setError(err.message || "Failed to start interview.");
    } finally {
      setStarting(false);
    }
  }

  async function beginRecording() {
    if (recording && streamRef.current && recorderRef.current) {
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("Browser does not support camera/mic capture.");
    }
    const stream = await navigator.mediaDevices.getUserMedia({
      video: true,
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    streamRef.current = stream;
    startBargeInMonitor(stream);
    if (videoRef.current) {
      videoRef.current.srcObject = stream;
      videoRef.current.muted = true;
      try {
        await videoRef.current.play();
      } catch {
        // ignore autoplay issues
      }
    }

    const preferredMimeTypes = [
      "video/webm;codecs=vp9,opus",
      "video/webm;codecs=vp8,opus",
      "video/webm",
    ];
    const mimeType = preferredMimeTypes.find((type) => MediaRecorder.isTypeSupported(type)) || "";
    const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);

    chunksRef.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        chunksRef.current.push(event.data);
      }
    };
    recorder.start(1000);
    recorderRef.current = recorder;
    setRecording(true);
  }

  async function submitAnswerText(rawAnswer, options = {}) {
    const answer = String(rawAnswer || "").trim();
    if (!sessionId || !answer) {
      return false;
    }
    if (submitInFlightRef.current) {
      return false;
    }

    const normalized = normalizeAnswer(answer);
    const now = Date.now();
    if (
      !options.force &&
      normalized &&
      normalized === lastSubmittedNormalizedRef.current &&
      now - lastSubmittedAtRef.current < 4000
    ) {
      return false;
    }

    submitInFlightRef.current = true;
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/app/live/${sessionId}/answer`, {
        method: "POST",
        headers: {
          ...authHeaders,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          answerText: answer,
          questionAskedAt: options.questionAskedAt || questionAskedAtRef.current || null,
          answerStartedAt: options.answerStartedAt || answerStartedAtRef.current || null,
          answerEndedAt: options.answerEndedAt || makeIsoNow(),
          transcriptConfidence:
            typeof options.transcriptConfidence === "number" ? options.transcriptConfidence : null,
        }),
      });
      if (response.status === 401) {
        throw new Error("Your login session expired. Please sign in again.");
      }
      if (!response.ok) {
        throw new Error(`Failed to submit answer (${response.status})`);
      }
      const payload = await response.json();
      setTurns((prev) => [
        ...prev,
        { role: "user", text: answer },
        ...(payload.nextQuestion ? [{ role: "assistant", text: payload.nextQuestion }] : []),
      ]);
      setLatestTranscript(answer);
      clearTranscriptDrafts();
      answerStartedAtRef.current = "";
      questionAskedAtRef.current = "";
      pendingTranscriptConfidenceRef.current = 0.75;
      setCurrentQuestion(payload.nextQuestion || "");
      setInterviewComplete(Boolean(payload.isInterviewComplete));
      shouldAutoListenRef.current = false;
      autoCaptureActiveRef.current = false;
      avatarHeardSpeakingRef.current = false;
      lastSubmittedNormalizedRef.current = normalized;
      lastSubmittedAtRef.current = now;
      if (autoListenTimerRef.current) {
        window.clearTimeout(autoListenTimerRef.current);
        autoListenTimerRef.current = null;
      }
      void syncLiveState(sessionId);
      return true;
    } catch (err) {
      if (String(err.message || "").toLowerCase().includes("expired")) {
        logout();
        navigate("/auth", { replace: true });
        return false;
      }
      setError(err.message || "Failed to submit answer.");
      return false;
    } finally {
      setSubmitting(false);
      submitInFlightRef.current = false;
    }
  }

  async function endInterviewAndAnalyze() {
    if (!sessionId || !canEndInterview) {
      return;
    }
    setEnding(true);
    setAnalysisStepIndex(0);
    setAnalysisProgress(6);
    setError("");
    shouldAutoListenRef.current = false;
    autoCaptureActiveRef.current = false;
    avatarHeardSpeakingRef.current = false;
    if (autoListenTimerRef.current) {
      window.clearTimeout(autoListenTimerRef.current);
      autoListenTimerRef.current = null;
    }
    stopListening();
    stopAvatarSpeech();
    try {
      const blob = await stopRecordingAndGetBlob();
      setAnalysisProgress(18);
      if (!blob || blob.size === 0) {
        throw new Error("No recording captured. Please allow camera/microphone access.");
      }

      const formData = new FormData();
      formData.append("video", blob, `live_interview_${sessionId}.webm`);
      formData.append("frameFps", "2");
      formData.append("windowSizeSeconds", "3.0");
      formData.append("useLearnedFusion", "false");

      setAnalysisProgress(32);
      const response = await fetch(`${API_BASE_URL}/app/live/${sessionId}/end`, {
        method: "POST",
        headers: authHeaders,
        body: formData,
      });
      setAnalysisProgress(82);
      if (response.status === 401) {
        throw new Error("Your login session expired. Please sign in again.");
      }
      if (!response.ok) {
        let detail = `End interview failed (${response.status})`;
        try {
          const payload = await response.json();
          if (payload?.detail) {
            detail = String(payload.detail);
          }
        } catch {
          // ignore parse failure
        }
        throw new Error(detail);
      }
      await response.json();
      setAnalysisStepIndex(ANALYSIS_STEPS.length - 1);
      setAnalysisProgress(100);
      await new Promise((resolve) => {
        window.setTimeout(resolve, 500);
      });
      clearStoredLiveSession();
      navigate(`/dashboard/${sessionId}`);
    } catch (err) {
      if (String(err.message || "").toLowerCase().includes("expired")) {
        logout();
        navigate("/auth", { replace: true });
        return;
      }
      setError(err.message || "Unable to end and analyze interview.");
    } finally {
      setEnding(false);
    }
  }

  async function stopRecordingAndGetBlob() {
    const recorder = recorderRef.current;
    if (!recorder) {
      return null;
    }
    if (recorder.state !== "inactive") {
      await new Promise((resolve) => {
        try {
          recorder.requestData();
        } catch {
          // ignore requestData failures
        }
        recorder.onstop = resolve;
        recorder.stop();
      });
    }
    const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "video/webm" });
    stopMediaResources();
    return blob;
  }

  function stopMediaResources() {
    stopBargeInMonitor();
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      try {
        recorderRef.current.stop();
      } catch {
        // ignore stop errors
      }
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    recorderRef.current = null;
    setRecording(false);
  }

  async function speakWithAvatar(text) {
    const cleanText = String(text || "").trim();
    if (!cleanText) {
      return;
    }

    stopAvatarSpeech();
    const speakToken = avatarSpeakTokenRef.current + 1;
    avatarSpeakTokenRef.current = speakToken;

    if (ENABLE_PROVIDER_AVATAR && avatarProviderEnabled) {
      const usedProvider = await speakWithProviderAvatar(cleanText, speakToken);
      if (usedProvider) {
        return;
      }
    }

    if (speakToken !== avatarSpeakTokenRef.current || cleanText !== currentQuestionRef.current) {
      return;
    }
    speakWithBrowserTts(cleanText);
  }

  function speakWithBrowserTts(text) {
    if (!window.speechSynthesis || !String(text || "").trim()) {
      setAvatarProviderStatus("Browser voice unavailable. Continuing without spoken avatar audio.");
      setAvatarSpeaking(false);
      return;
    }
    stopAvatarSpeech();
    const utterance = new SpeechSynthesisUtterance(String(text).trim());
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    utterance.onstart = () => setAvatarSpeaking(true);
    utterance.onend = () => setAvatarSpeaking(false);
    utterance.onerror = () => setAvatarSpeaking(false);
    window.speechSynthesis.speak(utterance);
  }

  async function speakWithProviderAvatar(text, speakToken) {
    const configuredProvider = String(avatarProviderName || "").toLowerCase();
    const expectSimliProvider = configuredProvider === "simli";

    const controller = new AbortController();
    let timeoutId = null;
    avatarPollTokenRef.current += 1;
    const pollToken = avatarPollTokenRef.current;
    setAvatarRenderStatus("requesting");
    setAvatarVideoUrl("");
    try {
      const timeoutMs = expectSimliProvider ? Math.max(6000, AVATAR_PROVIDER_REQUEST_TIMEOUT_MS) : AVATAR_PROVIDER_REQUEST_TIMEOUT_MS;
      timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
      const response = await fetch(`${API_BASE_URL}/app/live/avatar/speak`, {
        method: "POST",
        headers: {
          ...authHeaders,
          "Content-Type": "application/json",
        },
        signal: controller.signal,
        body: JSON.stringify({
          text,
          sessionId: sessionId || undefined,
        }),
      });
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
      if (response.status === 401) {
        throw new Error("Your login session expired. Please sign in again.");
      }
      if (!response.ok) {
        throw new Error(`Provider avatar request failed (${response.status})`);
      }

      const payload = await response.json();
      if (speakToken !== avatarSpeakTokenRef.current || text !== currentQuestionRef.current) {
        return true;
      }
      const providerVideoUrl = resolveProviderVideoUrl(payload);
      const responseProvider = String(payload.provider || "").toLowerCase() || "browser";
      const isSimliProvider = responseProvider === "simli";
      const simliConfigured = expectSimliProvider || isSimliProvider;
      if (!(expectSimliProvider && responseProvider === "browser")) {
        setAvatarProviderName(responseProvider);
      }
      setAvatarVideoUrl(providerVideoUrl);

      const warningText = Array.isArray(payload.warnings) ? payload.warnings.join(" ") : "";
      const statusText =
        payload.fallbackReason ||
        warningText ||
        (simliConfigured && !providerVideoUrl
          ? "Simli session ready. Using in-room avatar audio/video."
          : "Provider avatar response received.");
      setAvatarProviderStatus(statusText);

      if (providerVideoUrl) {
        setAvatarRenderStatus("ready");
      }

      // For Simli, avoid local audio playback to prevent dual/unsynced audio.
      // Simli room remote audio should be the only spoken path.
      const allowSimliLocalAudioFallback = simliConfigured && (!simliConnected || !SIMLI_PLAY_REMOTE_AUDIO);
      if (payload.audioUrl && (!simliConfigured || allowSimliLocalAudioFallback)) {
        const didPlayAudio = await playAvatarAudio(payload);
        if (didPlayAudio) {
          if (allowSimliLocalAudioFallback) {
            setAvatarProviderStatus("Simli stream not ready yet. Using local voice fallback for this question.");
          }
          return true;
        }
      }

      // Simli may still be connecting; allow browser fallback so prompts are still spoken.
      if (simliConfigured && !simliConnected && !providerVideoUrl && !payload.audioUrl) {
        setAvatarRenderStatus("connecting");
        setAvatarProviderStatus("Simli stream is still connecting. Waiting for avatar speech channel.");
        return false;
      }

      if (simliConfigured && !SIMLI_PLAY_REMOTE_AUDIO) {
        setAvatarProviderStatus(
          "Simli remote audio is disabled. Set VITE_SIMLI_PLAY_REMOTE_AUDIO=1 for avatar-only voice."
        );
        setAvatarRenderStatus("ready");
      }

      if (expectSimliProvider && responseProvider === "browser") {
        setAvatarRenderStatus("connecting");
        setAvatarProviderStatus(payload.fallbackReason || "Simli speech channel unavailable for this turn.");
        return false;
      }

      if (providerVideoUrl) {
        setAvatarRenderStatus("ready");
        setAvatarSpeaking(true);
        window.setTimeout(() => setAvatarSpeaking(false), 1800);
        return true;
      }

      if (payload.requestId && !isSimliProvider) {
        setAvatarRenderStatus("rendering");
        const ready = await pollAvatarRender(payload.requestId, payload.provider, pollToken);
        if (ready) {
          return true;
        }
      }

      // Simli stream handles voice/video in-room. Don't fallback to browser TTS.
      if (simliConfigured) {
        return true;
      }

      return false;
    } catch (err) {
      if (String(err.message || "").toLowerCase().includes("expired")) {
        logout();
        navigate("/auth", { replace: true });
        return true;
      }
      if (expectSimliProvider) {
        setAvatarRenderStatus("error");
        setAvatarProviderStatus("Simli avatar request failed for this turn. Falling back to browser voice.");
        return false;
      }
      setAvatarRenderStatus("error");
      setAvatarProviderStatus("Provider avatar failed. Falling back to browser TTS.");
      return false;
    } finally {
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
    }
  }

  async function connectSimliRoom(activeSessionId) {
    if (!activeSessionId || simliRoomRef.current) {
      return;
    }

    setSimliConnecting(true);
    setSimliError("");
    if (!simliConnectStartedAtRef.current) {
      simliConnectStartedAtRef.current = Date.now();
    }
    try {
      const response = await fetch(`${API_BASE_URL}/app/live/avatar/simli/session`, {
        method: "POST",
        headers: {
          ...authHeaders,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          sessionId: activeSessionId,
        }),
      });
      if (response.status === 401) {
        throw new Error("Your login session expired. Please sign in again.");
      }
      if (!response.ok) {
        let detail = `Simli room setup failed (${response.status})`;
        try {
          const payload = await response.json();
          if (payload?.detail) {
            detail = String(payload.detail);
          }
        } catch {
          // ignore
        }
        throw new Error(detail);
      }

      const payload = await response.json();
      const livekit = await loadLiveKitBrowserLibrary();
      const room = new livekit.Room();
      simliRoomRef.current = room;

      const attachTrack = (track) => {
        const trackId = String(track.sid || track.mediaStreamTrack?.id || "");
        if (trackId && simliTrackIdsRef.current.has(trackId)) {
          return;
        }
        if (trackId) {
          simliTrackIdsRef.current.add(trackId);
        }

        if (track.kind === livekit.Track.Kind.Video && simliVideoRef.current) {
          track.attach(simliVideoRef.current);
          setSimliConnected(true);
          simliConnectStartedAtRef.current = 0;
          setAvatarRenderStatus("ready");
          setAvatarProviderStatus("Simli avatar connected.");
        } else if (track.kind === livekit.Track.Kind.Audio) {
          if (!SIMLI_PLAY_REMOTE_AUDIO) {
            return;
          }
          const audioEl = track.attach();
          if (audioEl) {
            audioEl.autoplay = true;
            audioEl.playsInline = true;
            audioEl.style.display = "none";
            document.body.appendChild(audioEl);
            const playAttempt = audioEl.play();
            if (playAttempt && typeof playAttempt.catch === "function") {
              playAttempt.catch(() => {
                // autoplay can be blocked by browser policy; user gesture usually unlocks after Start Interview
              });
            }
            simliAudioElsRef.current.push(audioEl);
          }
        }
      };

      room.on(livekit.RoomEvent.TrackSubscribed, (track) => {
        attachTrack(track);
      });
      room.on(livekit.RoomEvent.TrackUnsubscribed, (track) => {
        const trackId = String(track.sid || track.mediaStreamTrack?.id || "");
        if (trackId) {
          simliTrackIdsRef.current.delete(trackId);
        }
        track.detach();
      });
      room.on(livekit.RoomEvent.Disconnected, () => {
        setSimliConnected(false);
      });
      room.on(livekit.RoomEvent.ActiveSpeakersChanged, (speakers) => {
        const hasRemoteSpeaker = Array.isArray(speakers)
          ? speakers.some((p) => p.identity !== payload.participantIdentity)
          : false;
        setAvatarSpeaking(hasRemoteSpeaker);
      });

      await room.connect(payload.wsUrl, payload.participantToken);
      setAvatarProviderStatus("Connected to Simli room. Waiting for avatar stream...");

      try {
        const micTrack = await livekit.createLocalAudioTrack();
        await room.localParticipant.publishTrack(micTrack);
        simliMicTrackRef.current = micTrack;
        setAvatarProviderStatus("Connected to Simli room with microphone published.");
      } catch {
        setAvatarProviderStatus("Connected to Simli room. Microphone publish failed.");
      }
    } catch (err) {
      if (String(err.message || "").toLowerCase().includes("expired")) {
        logout();
        navigate("/auth", { replace: true });
        return;
      }
      setSimliError(String(err.message || "Unable to connect Simli room."));
      setAvatarProviderStatus("Simli connection failed.");
      disconnectSimliRoom();
    } finally {
      setSimliConnecting(false);
    }
  }

  function disconnectSimliRoom() {
    simliConnectStartedAtRef.current = 0;
    simliTrackIdsRef.current.clear();
    if (simliMicTrackRef.current) {
      try {
        simliMicTrackRef.current.stop();
      } catch {
        // ignore cleanup failures
      }
      simliMicTrackRef.current = null;
    }
    if (simliAudioElsRef.current.length > 0) {
      simliAudioElsRef.current.forEach((el) => {
        try {
          el.pause();
          el.srcObject = null;
          el.src = "";
          if (el.parentNode) {
            el.parentNode.removeChild(el);
          }
        } catch {
          // ignore cleanup failures
        }
      });
      simliAudioElsRef.current = [];
    }
    if (simliRoomRef.current) {
      try {
        simliRoomRef.current.disconnect();
      } catch {
        // ignore disconnect failures
      }
      simliRoomRef.current = null;
    }
    if (simliVideoRef.current) {
      try {
        simliVideoRef.current.srcObject = null;
      } catch {
        // ignore cleanup failures
      }
    }
    setSimliConnected(false);
  }

  async function pollAvatarRender(requestId, provider, pollToken) {
    for (let attempt = 0; attempt < AVATAR_STATUS_POLL_ATTEMPTS; attempt += 1) {
      if (pollToken !== avatarPollTokenRef.current) {
        return false;
      }
      try {
        const response = await fetch(`${API_BASE_URL}/app/live/avatar/status`, {
          method: "POST",
          headers: {
            ...authHeaders,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            requestId,
            provider,
          }),
        });
        if (response.status === 401) {
          throw new Error("Your login session expired. Please sign in again.");
        }
        if (!response.ok) {
          throw new Error(`Avatar status polling failed (${response.status})`);
        }

        const payload = await response.json();
        const providerVideoUrl = resolveProviderVideoUrl(payload);
        const statusValue = String(payload.status || "rendering").toLowerCase();
        setAvatarRenderStatus(statusValue);
        if (payload.audioUrl) {
          const didPlayAudio = await playAvatarAudio(payload);
          return didPlayAudio;
        }
        if (providerVideoUrl) {
          setAvatarVideoUrl(providerVideoUrl);
          setAvatarProviderStatus("Human avatar generated. Playing rendered question.");
          return true;
        }
        if (statusValue === "error" || statusValue === "failed" || statusValue === "rejected") {
          setAvatarProviderStatus(payload.error || "Avatar generation failed at provider.");
          return false;
        }
      } catch (err) {
        if (String(err.message || "").toLowerCase().includes("expired")) {
          logout();
          navigate("/auth", { replace: true });
          return true;
        }
        setAvatarProviderStatus(err.message || "Avatar polling failed.");
        setAvatarRenderStatus("error");
        return false;
      }

      await new Promise((resolve) => {
        window.setTimeout(resolve, AVATAR_STATUS_POLL_INTERVAL_MS);
      });
    }

    setAvatarProviderStatus("Human avatar rendering timed out. Falling back to browser voice.");
    setAvatarRenderStatus("timeout");
    return false;
  }

  async function playAvatarAudio(payload) {
    const audioUrl = String(payload?.audioUrl || "").trim();
    if (!audioUrl) {
      return false;
    }

    stopAvatarSpeech();
    setAvatarRenderStatus("ready");

    const audio = new Audio(audioUrl);
    avatarAudioRef.current = audio;
    audio.onplay = () => setAvatarSpeaking(true);
    audio.onended = () => {
      setAvatarSpeaking(false);
    };
    audio.onpause = () => {
      if (!audio.ended) {
        setAvatarSpeaking(false);
      }
    };
    audio.onerror = () => {
      setAvatarSpeaking(false);
    };
    try {
      await audio.play();
      return true;
    } catch {
      return false;
    }
  }

  function stopAvatarSpeech() {
    avatarSpeakTokenRef.current += 1;
    avatarPollTokenRef.current += 1;
    if (avatarSpeakingTimeoutRef.current) {
      window.clearTimeout(avatarSpeakingTimeoutRef.current);
      avatarSpeakingTimeoutRef.current = null;
    }
    if (avatarAudioRef.current) {
      try {
        avatarAudioRef.current.ontimeupdate = null;
        avatarAudioRef.current.pause();
        avatarAudioRef.current.src = "";
      } catch {
        // ignore audio cleanup errors
      }
      avatarAudioRef.current = null;
    }
    if (avatarVideoRef.current) {
      try {
        avatarVideoRef.current.pause();
      } catch {
        // ignore video pause errors
      }
    }
    if (!window.speechSynthesis) {
      setAvatarSpeaking(false);
      return;
    }
    window.speechSynthesis.cancel();
    setAvatarSpeaking(false);
  }

  function startListening({ interruptAvatar = false } = {}) {
    const SpeechRecognitionClass = getSpeechRecognitionClass();
    if (!SpeechRecognitionClass) {
      setSttFallbackMode(true);
      setSttFallbackReason("Speech-to-text unavailable. Use fallback answer submit.");
      setError("Speech recognition is not supported in this browser. Use fallback answer submit.");
      return false;
    }
    if (recognitionRef.current || recognitionStartingRef.current) {
      return false;
    }
    if (avatarSpeaking && !interruptAvatar) {
      return false;
    }
    if (submitting || ending || interviewComplete || interviewPaused) {
      return false;
    }
    if (!interruptAvatar) {
      const msSinceAvatarEnded = Date.now() - Number(avatarSpeechEndedAtRef.current || 0);
      if (msSinceAvatarEnded >= 0 && msSinceAvatarEnded < POST_AVATAR_LISTEN_DELAY_MS) {
        if (autoListenTimerRef.current) {
          window.clearTimeout(autoListenTimerRef.current);
        }
        autoListenTimerRef.current = window.setTimeout(() => {
          startListening({ interruptAvatar: false });
        }, POST_AVATAR_LISTEN_DELAY_MS - msSinceAvatarEnded);
        return false;
      }
    }
    if (autoListenTimerRef.current) {
      window.clearTimeout(autoListenTimerRef.current);
      autoListenTimerRef.current = null;
    }
    setError("");
    clearTranscriptDrafts();
    pendingVoiceSubmitRef.current = "";
    forceSubmitOnStopRef.current = false;
    pendingTranscriptConfidenceRef.current = 0.75;
    if (interruptAvatar) {
      stopAvatarSpeech();
    }

    const recognition = new SpeechRecognitionClass();
    recognition.lang = "en-US";
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    // Keep recognition active across short pauses so answers are not truncated.
    recognition.continuous = true;

    recognition.onstart = () => {
      recognitionStartingRef.current = false;
      listeningStartedAtRef.current = Date.now();
      lastSpeechDetectedAtRef.current = Date.now();
      setSttFallbackMode(false);
      setSttFallbackReason("");
      setListening(true);
    };
    recognition.onresult = (event) => {
      let finalChunk = "";
      let interimChunk = "";
      for (let idx = event.resultIndex; idx < event.results.length; idx += 1) {
        const item = event.results[idx];
        const text = String(item[0]?.transcript || "").trim();
        if (!text) {
          continue;
        }
        if (item.isFinal) {
          finalChunk = `${finalChunk} ${text}`.trim();
        } else {
          interimChunk = `${interimChunk} ${text}`.trim();
        }
      }
      if (finalChunk) {
        transcriptFinalRef.current = appendUniqueText(transcriptFinalRef.current, finalChunk);
      }
      transcriptInterimRef.current = interimChunk;
      const merged = `${transcriptFinalRef.current} ${transcriptInterimRef.current}`.trim();
      if (!merged) {
        return;
      }
      const sanitizedMerged = stripLeadingQuestionEcho(merged, currentQuestionRef.current);
      const listenAgeMs = Date.now() - Number(listeningStartedAtRef.current || 0);
      if (!sanitizedMerged || isLikelyAvatarEcho(sanitizedMerged, currentQuestionRef.current, listenAgeMs)) {
        setRecognitionText("");
        setLatestTranscript("");
        setAnswerText("");
        setCommittedTranscript("");
        setInterimTranscript("");
        pendingVoiceSubmitRef.current = "";
        return;
      }
      const sanitizedCommitted = stripLeadingQuestionEcho(transcriptFinalRef.current, currentQuestionRef.current);
      const sanitizedInterim =
        sanitizedCommitted && sanitizedMerged.startsWith(sanitizedCommitted)
          ? sanitizedMerged.slice(sanitizedCommitted.length).trim()
          : sanitizedCommitted
            ? ""
            : sanitizedMerged;
      setCommittedTranscript(sanitizedCommitted);
      setInterimTranscript(sanitizedInterim);
      if (!answerStartedAtRef.current) {
        answerStartedAtRef.current = makeIsoNow();
      }
      lastSpeechDetectedAtRef.current = Date.now();
      setRecognitionText(sanitizedMerged);
      setLatestTranscript(sanitizedMerged);
      setAnswerText(sanitizedMerged);
      pendingVoiceSubmitRef.current = sanitizedMerged;
      if (silenceSubmitTimerRef.current) {
        window.clearTimeout(silenceSubmitTimerRef.current);
      }
      silenceSubmitTimerRef.current = window.setTimeout(async () => {
        if (recognitionRef.current) {
          const candidateText = String(pendingVoiceSubmitRef.current || "").trim();
          if (!candidateText) {
            return;
          }
          const silenceMs = Math.max(0, Date.now() - Number(lastSpeechDetectedAtRef.current || 0));
          const listeningMs = Math.max(0, Date.now() - Number(listeningStartedAtRef.current || 0));
          const decision = await evaluateTurnServerSide(candidateText, {
            silenceMs,
            listeningMs,
            isFinal: false,
          });
          if (decision?.action === "ignore_echo") {
            clearTranscriptDrafts();
            return;
          }
          if (decision?.shouldSubmit) {
            pendingTranscriptConfidenceRef.current =
              typeof decision?.confidenceHint === "number" ? Number(decision.confidenceHint) : 0.75;
            stopListening({ submitAfterStop: true });
          }
        }
      }, SILENCE_SUBMIT_MS);
    };
    recognition.onerror = (event) => {
      recognitionStartingRef.current = false;
      setListening(false);
      const errorCode = String(event?.error || "").toLowerCase();
      if (["not-allowed", "service-not-allowed", "network", "audio-capture"].includes(errorCode)) {
        setSttFallbackMode(true);
        setSttFallbackReason("Speech recognition had an issue. Continue with fallback submit.");
      }
    };
    recognition.onend = async () => {
      recognitionStartingRef.current = false;
      recognitionRef.current = null;
      setListening(false);
      const finalText =
        pendingVoiceSubmitRef.current.trim() ||
        answerTextRef.current.trim() ||
        latestTranscriptRef.current.trim();
      const shouldSubmit = forceSubmitOnStopRef.current;
      forceSubmitOnStopRef.current = false;
      const submitted = await maybeSubmitTranscript(finalText, {
        forceSubmit: shouldSubmit,
        isFinal: true,
      });
      if (submitted) {
        return;
      }
      if (autoCaptureActiveRef.current && !submitting && !ending && !interviewComplete && !interviewPaused) {
        window.setTimeout(() => {
          if (
            !recognitionRef.current &&
            autoCaptureActiveRef.current &&
            !avatarSpeakingRef.current &&
            !submitting &&
            !ending &&
            !interviewComplete &&
            !interviewPaused
          ) {
            startListening({ interruptAvatar: false });
          }
        }, 320);
      }
    };

    recognitionRef.current = recognition;
    recognitionStartingRef.current = true;
    try {
      recognition.start();
      return true;
    } catch {
      recognitionStartingRef.current = false;
      recognitionRef.current = null;
      setListening(false);
      setSttFallbackMode(true);
      setSttFallbackReason("Could not start speech recognition. Use fallback answer submit.");
      return false;
    }
  }

  function stopListening({ submitAfterStop = false, transcriptConfidence = 0.75 } = {}) {
    if (silenceSubmitTimerRef.current) {
      window.clearTimeout(silenceSubmitTimerRef.current);
      silenceSubmitTimerRef.current = null;
    }
    pendingTranscriptConfidenceRef.current = transcriptConfidence;
    forceSubmitOnStopRef.current = Boolean(submitAfterStop);
    if (!recognitionRef.current) {
      const finalText =
        pendingVoiceSubmitRef.current.trim() ||
        answerTextRef.current.trim() ||
        latestTranscriptRef.current.trim();
      if (submitAfterStop && finalText) {
        void maybeSubmitTranscript(finalText, {
          forceSubmit: true,
          isFinal: true,
        });
      }
      return;
    }
    try {
      recognitionRef.current.stop();
    } catch {
      // ignore stop errors
    }
    recognitionStartingRef.current = false;
    recognitionRef.current = null;
    setListening(false);
  }

  return (
    <main className={styles.shell}>
      {!sessionId ? (
        <section className={styles.card}>
          <h2>Start Interview</h2>
          <div className={styles.deviceCheckPanel}>
            <div className={styles.deviceCheckHeader}>
              <strong>Pre-Interview Device Check</strong>
              <button type="button" onClick={() => void runDeviceCheck()} disabled={deviceCheckRunning}>
                {deviceCheckRunning ? "Checking..." : "Run Check"}
              </button>
            </div>
            <div className={styles.deviceChecklist}>
              <span className={deviceCheck.camera ? styles.checkPass : styles.checkPending}>Camera</span>
              <span className={deviceCheck.microphone ? styles.checkPass : styles.checkPending}>Microphone</span>
              <span className={deviceCheck.network ? styles.checkPass : styles.checkPending}>Backend Network</span>
              <span className={deviceCheck.speaker ? styles.checkPass : styles.checkPending}>Speaker</span>
            </div>
            {deviceCheck.checked && deviceCheck.details ? (
              <p className={styles.deviceCheckDetail}>{deviceCheck.details}</p>
            ) : (
              <p className={styles.deviceCheckDetail}>Run this before starting. Camera, mic, and network are required.</p>
            )}
          </div>
          <form className={styles.form} onSubmit={startInterview}>
            <label htmlFor="job-role">Job Role</label>
            <input
              id="job-role"
              value={jobRole}
              onChange={(event) => setJobRole(event.target.value)}
              required
            />

            <label htmlFor="domain">Domain</label>
            <input
              id="domain"
              value={domain}
              onChange={(event) => setDomain(event.target.value)}
              required
            />

            <button type="submit" disabled={starting}>
              {starting ? "Starting..." : "Start Live Interview"}
            </button>
          </form>
          {recoveryMessage ? <p className={styles.infoMessage}>{recoveryMessage}</p> : null}
          <p className={styles.note}>
            If camera access is blocked, allow camera/microphone permissions and retry.
          </p>
        </section>
      ) : (
        <section className={styles.grid}>
          <article className={`${styles.card} ${styles.studioCard}`}>
            <h2>Interview Studio</h2>
            <div className={styles.mediaRow}>
              <div className={styles.mediaTile}>
                <div className={styles.mediaTileHeader}>
                  <strong>You</strong>
                  <span>{recording ? "Recording ON" : "Recording OFF"}</span>
                </div>
                <video ref={videoRef} className={styles.mediaVideo} autoPlay playsInline controls={false} />
              </div>
              <div className={styles.mediaTile}>
                <div className={styles.mediaTileHeader}>
                  <strong>AI Interviewer</strong>
                  <span>{avatarSpeaking ? "Speaking..." : "Waiting..."}</span>
                </div>
                {avatarVideoUrl ? (
                  <video
                    ref={avatarVideoRef}
                    className={styles.mediaVideo}
                    src={avatarVideoUrl}
                    controls
                    autoPlay
                    playsInline
                    onPlay={() => setAvatarSpeaking(true)}
                    onEnded={() => setAvatarSpeaking(false)}
                    onPause={() => setAvatarSpeaking(false)}
                  />
                ) : avatarProviderName === "simli" ? (
                  <div className={styles.avatarRenderPlaceholder}>
                    <video
                      ref={simliVideoRef}
                      className={styles.mediaVideo}
                      autoPlay
                      playsInline
                      controls={false}
                      muted={false}
                    />
                    <p>Status: {simliConnecting ? "connecting" : simliConnected ? "connected" : "waiting"}</p>
                    {simliError ? <p>{simliError}</p> : null}
                  </div>
                ) : (
                  <div className={styles.avatarRenderPlaceholder}>
                    <p>Status: {avatarRenderStatus || "ready"}</p>
                    <p>Browser voice mode active.</p>
                  </div>
                )}
                <p className={styles.avatarProviderLine}>
                  Mode: {avatarProviderEnabled ? `Provider (${avatarProviderName})` : "Browser TTS"}
                </p>
                {avatarProviderStatus ? <p className={styles.avatarHint}>{avatarProviderStatus}</p> : null}
              </div>
            </div>
            <div className={styles.meta}>
              <span>Session: {sessionId.slice(0, 8)}...</span>
              <span>Timer: {formatDuration(elapsedSeconds)}</span>
              <span>Markers: {timelineMarkers.length}</span>
            </div>
            <div className={styles.turnStateRow}>
              <span className={styles.turnStateLabel}>Turn State</span>
              <span className={`${styles.turnStatePill} ${styles[`turnState${turnState.replace(/\s+/g, "")}`] || ""}`}>
                {turnState}
              </span>
            </div>
            {recoveryMessage ? <p className={styles.infoMessage}>{recoveryMessage}</p> : null}
          </article>

          <article className={styles.card}>
            <h2>Interview Conversation</h2>
            <div className={styles.turnList}>
              {turns.map((turn, idx) => (
                <article key={`${turn.role}-${idx}`} className={turn.role === "assistant" ? styles.assistantTurn : styles.userTurn}>
                  <strong>{turn.role === "assistant" ? "AI Interviewer" : "You"}</strong>
                  <p>{turn.text}</p>
                </article>
              ))}
            </div>
            <div className={styles.transcriptPanel}>
              <strong>Live Transcript</strong>
              <p>{committedTranscript || (listening ? "Listening..." : "Waiting for your answer...")}</p>
              {interimTranscript ? <p className={styles.transcriptInterim}>Listening now: {interimTranscript}</p> : null}
            </div>

            {!interviewComplete ? (
              <div className={styles.form}>
                <div className={styles.voiceControls}>
                  <div className={styles.sessionControls}>
                    <button type="button" onClick={repeatCurrentQuestion} disabled={ending || submitting || interviewPaused}>
                      Repeat Question
                    </button>
                    <button type="button" onClick={skipCurrentQuestion} disabled={ending || submitting || interviewPaused}>
                      Skip Question
                    </button>
                    <button type="button" onClick={togglePauseInterview} disabled={ending || submitting}>
                      {interviewPaused ? "Resume Interview" : "Pause Interview"}
                    </button>
                  </div>
                  {listening ? (
                    <div className={styles.voiceButtons}>
                      <button
                        type="button"
                        onClick={() => {
                          stopListening({ submitAfterStop: true });
                        }}
                        disabled={submitting || ending}
                      >
                        Stop & Submit
                      </button>
                    </div>
                  ) : speechCaptureUnavailable ? (
                    <div className={styles.voiceButtons}>
                      <button
                        type="button"
                        onClick={() => {
                          void submitOfflineAnswer();
                        }}
                        disabled={submitting || ending || interviewPaused}
                      >
                        Submit Answer (No Transcript)
                      </button>
                    </div>
                  ) : (
                    <p className={styles.captureHint}>
                      Avatar asks automatically. Voice capture starts automatically after each question.
                    </p>
                  )}
                  {!sttAvailable ? (
                    <p className={styles.recognitionHint}>
                      Speech-to-text not available in this browser. Use fallback submit to keep interview flowing.
                    </p>
                  ) : null}
                  {sttFallbackMode ? <p className={styles.recognitionHint}>{sttFallbackReason}</p> : null}
                  {listening ? (
                    <p className={styles.captureHint}>
                      Your answer is captured from microphone audio and auto-submitted when you stop speaking.
                    </p>
                  ) : null}
                </div>
              </div>
            ) : (
              <div className={styles.completeBox}>
                <p>Interview questions completed. End interview to upload recording and run analysis.</p>
              </div>
            )}

            {!canEndInterview ? (
              <p className={styles.endHint}>
                Answer at least {MIN_ANSWERS_TO_END} questions to enable analysis.
              </p>
            ) : null}
            <button
              type="button"
              className={styles.endButton}
              disabled={ending || !canEndInterview}
              onClick={endInterviewAndAnalyze}
            >
              {ending ? "Analyzing..." : "End Interview & Analyze"}
            </button>
          </article>
        </section>
      )}

      {error ? <section className={styles.errorBox}>{error}</section> : null}
      {ending ? (
        <section className={styles.analysisOverlay}>
          <div className={styles.analysisCard}>
            <h2>Analyzing interview...</h2>
            <p>Please wait while we process video, audio, and transcript signals.</p>
            <div className={styles.analysisProgressMeta}>
              <span>{Math.round(analysisProgress)}%</span>
              <span>{ANALYSIS_STEPS[Math.min(analysisStepIndex, ANALYSIS_STEPS.length - 1)]}</span>
            </div>
            <div className={styles.analysisProgressTrack}>
              <div
                className={styles.analysisProgressFill}
                style={{ width: `${Math.max(0, Math.min(100, analysisProgress))}%` }}
              />
            </div>
            <ol className={styles.analysisSteps}>
              {ANALYSIS_STEPS.map((step, idx) => (
                <li
                  key={step}
                  className={`${styles.analysisStep} ${
                    idx < analysisStepIndex
                      ? styles.analysisStepDone
                      : idx === analysisStepIndex
                        ? styles.analysisStepActive
                        : ""
                  }`}
                >
                  {step}
                </li>
              ))}
            </ol>
          </div>
        </section>
      ) : null}
    </main>
  );
}

export default LiveInterview;
