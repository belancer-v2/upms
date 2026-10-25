export class ApiError extends Error {
  constructor(public status: number, message: string, public code = "") { super(message); }
}

export const store = {
  get token() { return typeof window === "undefined" ? "" : localStorage.getItem("fw_token") ?? ""; },
  set token(v: string) { if (v) localStorage.setItem("fw_token", v); else localStorage.removeItem("fw_token"); },
  /** Set once a person has signed in on this browser, so a missing access token is worth one silent refresh. */
  get hint() { return typeof window !== "undefined" && localStorage.getItem("fw_sess") === "1"; },
  set hint(v: boolean) { if (v) localStorage.setItem("fw_sess", "1"); else localStorage.removeItem("fw_sess"); },
  get prop() { return typeof window === "undefined" ? 0 : Number(localStorage.getItem("fw_prop") ?? 0); },
  set prop(v: number) { localStorage.setItem("fw_prop", String(v)); },
};

/** Where a signed-in person goes when the server says a password change is still pending. */
const CHANGE_PATH = "/change-password";
const NO_REFRESH = ["/auth/login", "/auth/refresh", "/auth/forgot-password", "/auth/reset-password", "/auth/verify-email", "/auth/resend-verification"];

/** When the access token stops working, read from its (unverified) payload. 0 if it cannot be read. */
function expiresAt(tok: string): number {
  try { return JSON.parse(atob(tok.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).exp * 1000; } catch { return 0; }
}

let inflight: Promise<boolean> | null = null;
/**
 * Swaps the refresh token (an HttpOnly cookie that scripts cannot read) for a new short-lived access token.
 * Concurrent callers share one request. The X-Requested-With header is the CSRF guard the server expects with the cookie.
 */
export function refreshSession(): Promise<boolean> {
  if (typeof window === "undefined") return Promise.resolve(false);
  if (!inflight) {
    inflight = (async () => {
      try {
        const res = await fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" }, body: "{}" });
        if (!res.ok) return false;
        const j = await res.json();
        if (!j.token) return false;
        store.token = j.token;
        return true;
      } catch { return false; }
    })().finally(() => { inflight = null; });
  }
  return inflight;
}

/** Refreshes a minute before the access token expires, so plain fetch() calls elsewhere keep working too. */
export async function ensureFresh(): Promise<void> {
  const tok = store.token;
  if (tok && expiresAt(tok) - Date.now() < 60_000) await refreshSession();
}

function signedOut() {
  store.token = ""; store.hint = false;
  if (typeof window !== "undefined") window.dispatchEvent(new Event("fw:signedout"));
}

/** fetch() with the sign-in and building headers, one transparent refresh on 401. For downloads and uploads that cannot use api(). */
export async function authFetch(input: string, init: RequestInit = {}): Promise<Response> {
  await ensureFresh();
  const go = () => fetch(input, { ...init, headers: { ...(init.headers as Record<string, string> | undefined), ...(store.token ? { Authorization: `Bearer ${store.token}` } : {}), ...(store.prop ? { "X-Property-Id": String(store.prop) } : {}) } });
  let res = await go();
  if (res.status === 401 && store.token) {
    if (await refreshSession()) res = await go(); else signedOut();
  }
  return res;
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}, retried = false): Promise<T> {
  if (!NO_REFRESH.includes(path)) await ensureFresh();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (store.token) headers.Authorization = `Bearer ${store.token}`;
  if (store.prop) headers["X-Property-Id"] = String(store.prop);
  const res = await fetch(`/api${path}`, { method: opts.method ?? (opts.body ? "POST" : "GET"), headers, body: opts.body ? JSON.stringify(opts.body) : undefined });
  if (res.status === 401 && !retried && store.token && !NO_REFRESH.includes(path)) {
    if (await refreshSession()) return api<T>(path, opts, true);   // once: a second 401 means the session really ended
    signedOut();
  }
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j); } catch {}
    const code = res.headers.get("X-Error-Code") ?? "";
    if (res.status === 403 && code === "password_change_required" && typeof window !== "undefined" && !window.location.pathname.startsWith(CHANGE_PATH)) window.location.href = `${CHANGE_PATH}?first=1`;
    throw new ApiError(res.status, msg, code);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

/** Money is stored as integer paisa. Always shown with Latin digits and "BDT", in both languages. */
export const money = (paisa: number | null | undefined) =>
  `BDT ${(Math.round(paisa ?? 0) / 100).toLocaleString("en-US", { maximumFractionDigits: 2 })}`;

export const fdate = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) : "";
export const ftime = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
