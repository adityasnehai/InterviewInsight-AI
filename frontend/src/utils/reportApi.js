export function buildReportFilename(sessionId) {
  const safeSessionId = String(sessionId || "session").replace(/[^a-zA-Z0-9_-]/g, "_");
  return `interview_report_${safeSessionId}.pdf`;
}

export function buildReportRequestPayload({ userName, chartSnapshots } = {}) {
  const hasSnapshots = Boolean(chartSnapshots && Object.keys(chartSnapshots).length);
  return {
    includeChartSnapshots: hasSnapshots,
    chartSnapshots: hasSnapshots ? chartSnapshots : undefined,
    userName: userName || undefined,
    format: "pdf",
  };
}

export async function fetchReportTemplate({
  apiBaseUrl,
  sessionId,
  userName,
  chartSnapshots,
  token,
  scoped = false,
  fetchImpl = fetch,
}) {
  const payload = buildReportRequestPayload({ userName, chartSnapshots });
  const endpoint = scoped
    ? `${apiBaseUrl}/app/me/sessions/${sessionId}/report`
    : `${apiBaseUrl}/reports/${sessionId}/generate`;
  const headers = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetchImpl(endpoint, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const errorBody = await response.json();
      if (errorBody?.detail) {
        detail = String(errorBody.detail);
      }
    } catch {
      // Ignore JSON parse failures and use the default message.
    }
    throw new Error(detail);
  }

  return response.json();
}
