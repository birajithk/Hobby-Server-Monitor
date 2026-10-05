export class ApiError extends Error {
  constructor(
    message,
    status,
    body = null,
  ) {
    super(message);

    this.name =
      "ApiError";

    this.status =
      status;

    this.body =
      body;
  }
}


export async function apiRequest(
  path,
  options = {},
) {
  const {
    headers = {},
    ...requestOptions
  } = options;

  const response =
    await fetch(
      path,
      {
        credentials:
          "same-origin",

        ...requestOptions,

        headers: {
          Accept:
            "application/json",

          ...headers,
        },
      },
    );


  let body = null;

  const contentType =
    response.headers.get(
      "content-type",
    ) || "";


  if (
    contentType.includes(
      "application/json",
    )
  ) {
    body =
      await response.json();
  }


  if (!response.ok) {
    throw new ApiError(
      body?.description ||
        body?.title ||
        (
          `Request failed with ` +
          `status ${response.status}`
        ),
      response.status,
      body,
    );
  }


  return body;
}


export function getCurrentUser() {
  return apiRequest(
    "/api/me",
  );
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
    `/api/containers/${
      encodeURIComponent(
        containerId,
      )
    }/metrics/latest`,
  );
}


export function getMetricHistory(
  containerId,
  range = "1h",
) {
  return apiRequest(
    `/api/containers/${
      encodeURIComponent(
        containerId,
      )
    }/metrics/history?range=${
      encodeURIComponent(
        range,
      )
    }`,
  );
}


export function executeContainerCommand(
  containerId,
  command,
  csrfToken,
) {
  return apiRequest(
    `/api/containers/${
      encodeURIComponent(
        containerId,
      )
    }/exec`,
    {
      method:
        "POST",

      headers: {
        "Content-Type":
          "application/json",

        "X-CSRF-Token":
          csrfToken,
      },

      body:
        JSON.stringify({
          command,
        }),
    },
  );
}