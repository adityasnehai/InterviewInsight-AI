import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { buildReportFilename, fetchReportTemplate } from "../utils/reportApi";
import { generateInterviewReportPdf } from "../utils/reportPdf";
import styles from "./ReportGenerator.module.css";

const DEFAULT_API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function captureChartSnapshots(snapshotTargets) {
  if (!snapshotTargets || typeof document === "undefined") {
    return {};
  }

  const targets = Object.entries(snapshotTargets);
  if (!targets.length) {
    return {};
  }

  const { default: html2canvas } = await import("html2canvas");
  const snapshots = {};

  for (const [snapshotKey, selector] of targets) {
    if (!selector || typeof selector !== "string") {
      continue;
    }
    const element = document.querySelector(selector);
    if (!element) {
      continue;
    }
    const canvas = await html2canvas(element, {
      backgroundColor: "#ffffff",
      scale: 2,
      useCORS: true,
      logging: false,
    });
    snapshots[snapshotKey] = canvas.toDataURL("image/png");
  }

  return snapshots;
}

function ReportGenerator({
  sessionId,
  userName,
  snapshotTargets,
  apiBaseUrl = DEFAULT_API_BASE_URL,
}) {
  const { token } = useAuth();
  const [isGenerating, setIsGenerating] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [statusVariant, setStatusVariant] = useState("idle");

  async function handleDownloadReport() {
    if (!sessionId || isGenerating) {
      return;
    }

    setIsGenerating(true);
    setStatusVariant("idle");
    setStatusMessage("Generating your report...");

    try {
      const chartSnapshots = await captureChartSnapshots(snapshotTargets);
      const reportData = await fetchReportTemplate({
        apiBaseUrl,
        sessionId,
        userName,
        chartSnapshots,
        token,
        scoped: true,
      });
      await generateInterviewReportPdf({
        reportPayload: reportData,
        filename: buildReportFilename(sessionId),
      });
      setStatusVariant("success");
      setStatusMessage("Report downloaded successfully.");
    } catch (error) {
      setStatusVariant("error");
      setStatusMessage(error.message || "Failed to generate report.");
      window.alert(error.message || "Failed to generate report.");
    } finally {
      setIsGenerating(false);
    }
  }

  return (
    <div className={styles.reportGenerator}>
      <button
        type="button"
        className={styles.downloadButton}
        onClick={handleDownloadReport}
        disabled={isGenerating}
      >
        {isGenerating ? (
          <>
            <span className={styles.spinner} aria-hidden="true" />
            Generating...
          </>
        ) : (
          "Download Full Report"
        )}
      </button>
      {statusMessage ? (
        <p
          role="status"
          className={`${styles.statusMessage} ${
            statusVariant === "success" ? styles.success : statusVariant === "error" ? styles.error : ""
          }`}
        >
          {statusMessage}
        </p>
      ) : null}
    </div>
  );
}

export default ReportGenerator;
