export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export const store = {
  get token() { return typeof window === "undefined" ? "" : localStorage.getItem("fw_token") ?? ""; },
  set token(v: string) { if (v) localStorage.setItem("fw_token", v); else localStorage.removeItem("fw_token"); },
  get prop() { return typeof window === "undefined" ? 0 : Number(localStorage.getItem("fw_prop") ?? 0); },
  set prop(v: number) { localStorage.setItem("fw_prop", String(v)); },
};

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (store.token) headers.Authorization = `Bearer ${store.token}`;
  if (store.prop) headers["X-Property-Id"] = String(store.prop);
  const res = await fetch(`/api${path}`, { method: opts.method ?? (opts.body ? "POST" : "GET"), headers, body: opts.body ? JSON.stringify(opts.body) : undefined });
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j); } catch {}
    throw new ApiError(res.status, msg);
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
