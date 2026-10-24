"use client";
import { useEffect, useState } from "react";
import { store } from "@/lib/api";

export type PersonKind = "user" | "occupant" | "staff";
type Index = Record<PersonKind, Record<string, number>>;

/* Which people have a photo (and its version) in the current building. Loaded once, shared by every Avatar on the page. */
let index: Index | null = null; let indexKey = ""; let inflight: Promise<void> | null = null;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((f) => f());

export const authHeaders = (): Record<string, string> => {
  const h: Record<string, string> = {};
  if (store.token) h.Authorization = `Bearer ${store.token}`;
  if (store.prop) h["X-Property-Id"] = String(store.prop);
  return h;
};

export function refreshPhotos(): Promise<void> {
  const key = `${store.token}|${store.prop}`;
  inflight = fetch("/api/profiles/photos", { headers: authHeaders() })
    .then((r) => (r.ok ? r.json() : null))
    .then((d) => { if (d) { index = d; indexKey = key; } })
    .catch(() => {})
    .finally(() => { inflight = null; notify(); });
  return inflight;
}

function usePhotoIndex() {
  const [, tick] = useState(0);
  useEffect(() => {
    const f = () => tick((n) => n + 1); listeners.add(f);
    if (!inflight && (!index || indexKey !== `${store.token}|${store.prop}`)) refreshPhotos();
    return () => { listeners.delete(f); };
  }, []);
  return index;
}

/* Photo bytes are fetched with the sign-in token (an <img> tag cannot send it) and kept as blob URLs, one per photo version. */
const blobs = new Map<string, Promise<string>>();
function blobFor(kind: PersonKind, id: number, ver: number): Promise<string> {
  const key = `${kind}/${id}/${ver}`;
  let p = blobs.get(key);
  if (!p) {
    p = fetch(`/api/profiles/${kind}/${id}/photo?v=${ver}`, { headers: authHeaders() })
      .then((r) => { if (!r.ok) throw new Error("no photo"); return r.blob(); })
      .then((b) => URL.createObjectURL(b));
    p.catch(() => blobs.delete(key));
    blobs.set(key, p);
  }
  return p;
}

const initials = (name: string) => {
  const w = name.replace(/^(dr|mr|mrs|ms|md)\.?\s+/i, "").trim().split(/\s+/).filter(Boolean);
  return ((w[0]?.[0] ?? "?") + (w.length > 1 ? w[w.length - 1][0] : "")).toUpperCase();
};
const hue = (name: string) => { let h = 0; for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360; return h; };

/** Round photo of a person, or coloured initials when there is none. Safe to use anywhere a name appears. */
export function Avatar({ kind, id, name, size = 36, ver }: { kind: PersonKind; id?: number | null; name: string; size?: number; ver?: number }) {
  const idx = usePhotoIndex();
  const v = id ? (ver ?? idx?.[kind]?.[String(id)] ?? 0) : 0;
  const [src, setSrc] = useState("");
  useEffect(() => {
    let live = true; setSrc("");
    if (id && v) blobFor(kind, id, v).then((u) => live && setSrc(u)).catch(() => {});
    return () => { live = false; };
  }, [kind, id, v]);
  const box: React.CSSProperties = { width: size, height: size, borderRadius: "50%", flex: "none", display: "inline-flex", alignItems: "center", justifyContent: "center", overflow: "hidden", verticalAlign: "middle" };
  if (src) return <img src={src} alt="" width={size} height={size} style={{ ...box, objectFit: "cover" }} />;
  const h = hue(name || "?");
  return <span aria-hidden style={{ ...box, background: `hsl(${h} 45% 40%)`, color: "#fff", fontWeight: 800, fontSize: Math.max(11, Math.round(size * 0.38)) }}>{initials(name || "?")}</span>;
}
