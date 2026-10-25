"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ensureFresh, refreshSession, store } from "./api";

export type Prop = { id: number; name: string; name_bn: string; city: string; org_id: number; org_name: string; roles: string[]; features: string[]; plan: string; sub_status: string; org_status: string };
export type Me = { id: number; name: string; name_bn: string; email: string; phone: string; lang: string; saas_role: string | null; must_change_password?: boolean };
type AuthState = {
  ready: boolean; user: Me | null; properties: Prop[]; prop: Prop | null; roles: string[];
  setProp: (id: number) => void; login: (email: string, password: string) => Promise<{ must_change_password: boolean }>; logout: () => void;
  has: (...r: string[]) => boolean; feature: (key: string) => boolean; saas: (...r: string[]) => boolean; reload: () => Promise<void>;
};
const Ctx = createContext<AuthState>(null as unknown as AuthState);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<Me | null>(null);
  const [properties, setProps] = useState<Prop[]>([]);
  const [propId, setPropId] = useState(0);

  const apply = useCallback((d: { user: Me; properties: Prop[] }) => {
    setUser(d.user); setProps(d.properties);
    if (d.user.must_change_password && !window.location.pathname.startsWith("/change-password")) window.location.replace("/change-password?first=1");   // temporary password: nothing else until it is changed
    const saved = store.prop;
    const pick = d.properties.find((p) => p.id === saved) ?? d.properties[0];
    if (pick) { store.prop = pick.id; setPropId(pick.id); } else setPropId(0);
  }, []);

  const reload = useCallback(async () => {
    if (!store.token && !(store.hint && await refreshSession())) { setReady(true); return; }   // no token but a sign-in was seen here: try the refresh cookie once
    try { apply(await api("/me")); } catch { store.token = ""; setUser(null); }
    setReady(true);
  }, [apply]);
  useEffect(() => { reload(); }, [reload]);
  // Keep the short-lived access token fresh so plain fetch() calls keep working, and drop to the login screen when the session has ended.
  useEffect(() => {
    const tick = () => { if (store.token) ensureFresh(); };
    const gone = () => { setUser(null); setProps([]); setPropId(0); };
    const timer = window.setInterval(tick, 60_000);
    window.addEventListener("focus", tick); document.addEventListener("visibilitychange", tick); window.addEventListener("fw:signedout", gone);
    return () => { window.clearInterval(timer); window.removeEventListener("focus", tick); document.removeEventListener("visibilitychange", tick); window.removeEventListener("fw:signedout", gone); };
  }, []);

  const login = async (email: string, password: string) => {
    const d = await api("/auth/login", { body: { email, password } });
    store.token = d.token; store.hint = true; apply(d); setReady(true);
    return { must_change_password: !!d.must_change_password };
  };
  const logout = () => {
    // revoke the session on the server (best effort), then forget it here
    fetch("/api/auth/logout", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-Requested-With": "fetch", ...(store.token ? { Authorization: `Bearer ${store.token}` } : {}) }, body: "{}" })
      .catch(() => {}).finally(() => { store.token = ""; store.hint = false; setUser(null); setProps([]); setPropId(0); window.location.href = "/login"; });
  };
  const setProp = (id: number) => { store.prop = id; setPropId(id); };
  const prop = properties.find((p) => p.id === propId) ?? null;
  const roles = prop?.roles ?? [];
  const value = useMemo<AuthState>(() => ({
    ready, user, properties, prop, roles, setProp, login, logout, reload,
    has: (...r) => r.some((x) => roles.includes(x)) || user?.saas_role === "SUPER_ADMIN" || user?.saas_role === "SAAS_ADMIN",
    feature: (k) => !!prop?.features.includes(k),
    saas: (...r) => !!user?.saas_role && (r.length === 0 || r.includes(user.saas_role)),
  }), [ready, user, properties, prop, roles, reload]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
export const useAuth = () => useContext(Ctx);
