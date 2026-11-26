/** Tiny API client: relative URLs only, error-envelope aware. */

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function apiGet(path, params) {
  let url = path;
  if (params) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") qs.set(k, v);
    }
    const s = qs.toString();
    if (s) url += `?${s}`;
  }
  const resp = await fetch(url, { headers: { Accept: "application/json" } });
  return unwrap(resp);
}

export async function apiPost(path, body) {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body || {}),
  });
  return unwrap(resp);
}

async function unwrap(resp) {
  if (resp.status === 304) return null;
  let data = null;
  try {
    data = await resp.json();
  } catch {
    /* non-JSON body */
  }
  if (!resp.ok) {
    const err = data && data.error ? data.error : {};
    throw new ApiError(resp.status, err.code || "http_error", err.message || `HTTP ${resp.status}`);
  }
  return data;
}
