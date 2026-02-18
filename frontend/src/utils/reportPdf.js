import { jsPDF } from "jspdf";
import { buildReportContentStructure, toDisplayLabel } from "./reportContent";

function ensurePageSpace(doc, yPosition, requiredHeight) {
  const pageHeight = doc.internal.pageSize.getHeight();
  if (yPosition + requiredHeight < pageHeight - 10) {
    return yPosition;
  }
  doc.addPage();
  return 16;
}

function writeParagraph(doc, text, x, y, maxWidth, lineHeight = 5.2) {
  const lines = doc.splitTextToSize(String(text || ""), maxWidth);
  doc.text(lines, x, y);
  return y + lines.length * lineHeight;
}

export async function generateInterviewReportPdf({ reportPayload, filename, jsPdfImpl = jsPDF }) {
  const content = buildReportContentStructure(reportPayload);
  const doc = new jsPdfImpl({ orientation: "portrait", unit: "mm", format: "a4" });

  const margin = 14;
  const contentWidth = doc.internal.pageSize.getWidth() - margin * 2;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(21);
  doc.text(content.title, margin, 28);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(11);
  doc.text(`Generated: ${new Date(content.generatedAt || Date.now()).toLocaleString()}`, margin, 36);

  let y = 48;
  doc.setFont("helvetica", "bold");
  doc.text("Session Metadata", margin, y);
  y += 6;
  doc.setFont("helvetica", "normal");
  Object.entries(content.metadata).forEach(([key, value]) => {
    y = ensurePageSpace(doc, y, 8);
    const line = `${toDisplayLabel(key)}: ${value ?? "-"}`;
    y = writeParagraph(doc, line, margin, y, contentWidth);
  });

  y = ensurePageSpace(doc, y + 4, 25);
  doc.setFont("helvetica", "bold");
  doc.text("Overall Scores", margin, y);
  y += 6;
  doc.setFont("helvetica", "normal");
  content.overallScores.forEach((item) => {
    y = ensurePageSpace(doc, y, 8);
    doc.text(`${item.label}: ${item.value.toFixed(1)}`, margin, y);
    y += 5;
  });

  y = ensurePageSpace(doc, y + 3, 30);
  doc.setFont("helvetica", "bold");
  doc.text("Segment Breakdown", margin, y);
  y += 6;
  doc.setFont("helvetica", "normal");
  content.segmentSummaries.forEach((segment) => {
    y = ensurePageSpace(doc, y, 22);
    doc.setFont("helvetica", "bold");
    doc.text(`${segment.label} (${segment.segmentId})`, margin, y);
    y += 5;
    doc.setFont("helvetica", "normal");
    doc.text(`Time: ${segment.timeRange} | Dominant Emotion: ${segment.dominantEmotion}`, margin, y);
    y += 5;
    segment.scores.forEach((score) => {
      y = ensurePageSpace(doc, y, 7);
      doc.text(`- ${score.label}: ${score.value.toFixed(1)}`, margin + 3, y);
      y += 4.5;
    });
    y += 1.5;
  });

  y = ensurePageSpace(doc, y + 4, 28);
  doc.setFont("helvetica", "bold");
  doc.text("Feedback Summary", margin, y);
  y += 6;
  doc.setFont("helvetica", "normal");
  content.feedbackMessages.forEach((message) => {
    y = ensurePageSpace(doc, y, 10);
    y = writeParagraph(doc, `- ${message}`, margin, y, contentWidth);
  });

  y = ensurePageSpace(doc, y + 2, 20);
  doc.setFont("helvetica", "bold");
  doc.text("Top Strengths", margin, y);
  y += 5;
  doc.setFont("helvetica", "normal");
  content.strengths.forEach((item) => {
    y = ensurePageSpace(doc, y, 10);
    y = writeParagraph(doc, `- ${item}`, margin, y, contentWidth);
  });

  y = ensurePageSpace(doc, y + 2, 20);
  doc.setFont("helvetica", "bold");
  doc.text("Areas to Improve", margin, y);
  y += 5;
  doc.setFont("helvetica", "normal");
  content.improvements.forEach((item) => {
    y = ensurePageSpace(doc, y, 10);
    y = writeParagraph(doc, `- ${item}`, margin, y, contentWidth);
  });

  Object.entries(content.chartSnapshots).forEach(([label, dataUrl]) => {
    if (typeof dataUrl !== "string" || !dataUrl.startsWith("data:image/")) {
      return;
    }
    doc.addPage();
    doc.setFont("helvetica", "bold");
    doc.setFontSize(14);
    doc.text(`Chart Snapshot: ${toDisplayLabel(label)}`, margin, 18);
    const imageFormat = dataUrl.startsWith("data:image/jpeg") ? "JPEG" : "PNG";
    doc.addImage(dataUrl, imageFormat, margin, 24, contentWidth, 120, undefined, "FAST");
  });

  doc.save(filename || "interview_report.pdf");
  return content;
}
