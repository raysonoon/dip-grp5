const ENVIRONMENT = import.meta.env ?? globalThis.process?.env ?? {};
const configuredDevUserId = String(ENVIRONMENT.VITE_DEV_USER_ID ?? "").trim();

export const DEV_USER_TOKEN = /^[1-9]\d*$/.test(configuredDevUserId)
  ? configuredDevUserId
  : null;
export const DEV_USER_ID = DEV_USER_TOKEN === null ? null : Number(DEV_USER_TOKEN);
export const API_BASE_URL = String(ENVIRONMENT.VITE_API_BASE_URL ?? "")
  .trim()
  .replace(/\/+$/, "");

const DEFAULT_TIMEOUT_MS = 15_000;

export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export class ApiNetworkError extends Error {
  constructor(message, cause) {
    super(message, { cause });
    this.name = "ApiNetworkError";
  }
}

export class ApiResponseError extends Error {
  constructor(message, status, cause) {
    super(message, { cause });
    this.name = "ApiResponseError";
    this.status = status;
  }
}

export class ApiTimeoutError extends Error {
  constructor(timeoutMs) {
    super(`Request timed out after ${timeoutMs}ms`);
    this.name = "ApiTimeoutError";
    this.timeoutMs = timeoutMs;
  }
}

export class ApiAuthConfigurationError extends Error {
  constructor() {
    super("Set VITE_DEV_USER_ID to a seeded user ID before changing reviews");
    this.name = "ApiAuthConfigurationError";
  }
}

export function apiUrl(path) {
  if (/^https?:\/\//i.test(path)) return path;
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}

function errorMessage(payload, status) {
  if (typeof payload === "string" && payload.trim()) return payload;
  if (typeof payload?.detail === "string") return payload.detail;
  if (Array.isArray(payload?.detail)) {
    return payload.detail
      .map((issue) => issue?.msg)
      .filter(Boolean)
      .join(", ");
  }
  return `Request failed with status ${status}`;
}

async function request(
  path,
  {
    method = "GET",
    body,
    signal,
    auth = true,
    timeoutMs = DEFAULT_TIMEOUT_MS,
  } = {},
) {
  const headers = {};
  if (auth) {
    if (DEV_USER_TOKEN === null) throw new ApiAuthConfigurationError();
    headers["X-Dev-User-Id"] = DEV_USER_TOKEN;
  }
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const abortFromCaller = () => controller.abort(signal?.reason);
  if (signal?.aborted) abortFromCaller();
  else signal?.addEventListener("abort", abortFromCaller, { once: true });

  try {
    let response;
    try {
      response = await fetch(apiUrl(path), {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
    } catch (error) {
      if (timedOut) throw new ApiTimeoutError(timeoutMs);
      if (signal?.aborted) throw error;
      throw new ApiNetworkError("Could not connect to the API", error);
    }

    let payload = null;
    if (response.status !== 204) {
      const contentType = response.headers.get("content-type") ?? "";
      try {
        payload = contentType.includes("application/json")
          ? await response.json()
          : await response.text();
      } catch (error) {
        if (timedOut) throw new ApiTimeoutError(timeoutMs);
        if (signal?.aborted) throw error;
        throw new ApiResponseError("API response body is malformed", response.status, error);
      }
    }

    if (!response.ok) {
      throw new ApiError(errorMessage(payload, response.status), response.status, payload);
    }
    return payload;
  } finally {
    clearTimeout(timeoutId);
    signal?.removeEventListener("abort", abortFromCaller);
  }
}

export const apiClient = {
  get(path, options) {
    return request(path, options);
  },
  post(path, body, options) {
    return request(path, { ...options, method: "POST", body });
  },
  patch(path, body, options) {
    return request(path, { ...options, method: "PATCH", body });
  },
  delete(path, options) {
    return request(path, { ...options, method: "DELETE" });
  },
};
