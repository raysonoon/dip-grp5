export const TEST_USER_TOKEN = "2";
export const TEST_USER_ID = Number(TEST_USER_TOKEN);
export const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

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
  if (auth) headers["X-Dev-User-Id"] = TEST_USER_TOKEN;
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

  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (error) {
    if (timedOut) throw new ApiTimeoutError(timeoutMs);
    if (signal?.aborted) throw error;
    throw new ApiNetworkError("Could not connect to the API", error);
  } finally {
    clearTimeout(timeoutId);
    signal?.removeEventListener("abort", abortFromCaller);
  }

  let payload = null;
  if (response.status !== 204) {
    const contentType = response.headers.get("content-type") ?? "";
    try {
      payload = contentType.includes("application/json")
        ? await response.json()
        : await response.text();
    } catch (error) {
      throw new ApiResponseError("API response body is malformed", response.status, error);
    }
  }

  if (!response.ok) {
    throw new ApiError(errorMessage(payload, response.status), response.status, payload);
  }
  return payload;
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
