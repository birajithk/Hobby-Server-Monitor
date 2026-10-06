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

export function getAdminUsers() {
  return apiRequest(
    "/api/admin/users",
  );
}


export function getAdminUser(
  userId,
) {
  return apiRequest(
    `/api/admin/users/${
      encodeURIComponent(
        userId,
      )
    }`,
  );
}


export function updateUserRole(
  userId,
  role,
  csrfToken,
) {
  return apiRequest(
    `/api/admin/users/${
      encodeURIComponent(
        userId,
      )
    }/role`,
    {
      method:
        "PATCH",

      headers: {
        "Content-Type":
          "application/json",

        "X-CSRF-Token":
          csrfToken,
      },

      body:
        JSON.stringify({
          role,
        }),
    },
  );
}


export function revokeUser(
  userId,
  csrfToken,
) {
  return apiRequest(
    `/api/admin/users/${
      encodeURIComponent(
        userId,
      )
    }/revoke`,
    {
      method:
        "POST",

      headers: {
        "Content-Type":
          "application/json",

        "X-CSRF-Token":
          csrfToken,
      },
    },
  );
}


export function updateUserQuota(
  userId,
  quota,
  csrfToken,
) {
  return apiRequest(
    `/api/admin/users/${
      encodeURIComponent(
        userId,
      )
    }/quota`,
    {
      method:
        "PUT",

      headers: {
        "Content-Type":
          "application/json",

        "X-CSRF-Token":
          csrfToken,
      },

      body:
        JSON.stringify(
          quota,
        ),
    },
  );
}

export function getAdminContainerAccess(containerId) {
  return apiRequest(
    `/api/admin/containers/${encodeURIComponent(containerId)}/access`,
  );
}

export function assignContainerAccess(
  containerId,
  userId,
  csrfToken,
) {
  return apiRequest(
    `/api/admin/containers/${encodeURIComponent(containerId)}/access/${encodeURIComponent(userId)}`,
    {
      method: "POST",
      headers: {
        "X-CSRF-Token": csrfToken,
      },
    },
  );
}

export function revokeContainerAccess(
  containerId,
  userId,
  csrfToken,
) {
  return apiRequest(
    `/api/admin/containers/${encodeURIComponent(containerId)}/access/${encodeURIComponent(userId)}`,
    {
      method: "DELETE",
      headers: {
        "X-CSRF-Token": csrfToken,
      },
    },
  );
}

export function transferContainerOwner(
  containerId,
  newOwnerId,
  keepPreviousOwnerAccess,
  csrfToken,
) {
  return apiRequest(
    `/api/admin/containers/${encodeURIComponent(containerId)}/transfer-owner`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify({
        new_owner_id: newOwnerId,
        keep_previous_owner_access: keepPreviousOwnerAccess,
      }),
    },
  );
}

export function getAdminHost() {
  return apiRequest("/api/admin/host");
}

export function getAdminAllocations() {
  return apiRequest("/api/admin/allocations");
}

export function createManagedContainer(payload, csrfToken) {
  return apiRequest("/api/admin/containers", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken,
    },
    body: JSON.stringify(payload),
  });
}