export class ApiError extends Error {
  constructor(message, status, body = null) {
    super(message);

    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}


export async function apiRequest(
  path,
  options = {},
) {
  const response = await fetch(path, {
    credentials: "same-origin",

    headers: {
      Accept: "application/json",
      ...(options.headers || {}),
    },

    ...options,
  });

  let body = null;

  const contentType =
    response.headers.get("content-type") || "";

  if (
    contentType.includes(
      "application/json",
    )
  ) {
    body = await response.json();
  }

  if (!response.ok) {
    throw new ApiError(
      body?.description ||
        body?.title ||
        `Request failed with status ${response.status}`,
      response.status,
      body,
    );
  }

  return body;
}


export function getCurrentUser() {
  return apiRequest("/api/me");
}


export function getContainers() {
  return apiRequest(
    "/api/containers",
  );
}


export function getMyQuota() {
  return apiRequest(
    "/api/me/quota",
  );
}


export function getLatestMetrics(
  containerId,
) {
  return apiRequest(
    `/api/containers/${encodeURIComponent(
      containerId,
    )}/metrics/latest`,
  );
}


export function getMetricHistory(
  containerId,
  range = "1h",
) {
  return apiRequest(
    `/api/containers/${encodeURIComponent(
      containerId,
    )}/metrics/history?range=${encodeURIComponent(
      range,
    )}`,
  );
}
