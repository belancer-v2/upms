import { ApiError, authFetch } from "./api";

/** Downloads a file the API protects behind the sign-in (a plain link cannot send the Authorization header). */
export async function downloadFile(path: string, fallbackName: string): Promise<string> {
  const res = await authFetch(`/api${path}`);
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j); } catch { /* not JSON */ }
    throw new ApiError(res.status, msg);
  }
  const cd = res.headers.get("Content-Disposition") ?? "";
  const name = /filename="?([^";]+)"?/i.exec(cd)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
  return name;
}
