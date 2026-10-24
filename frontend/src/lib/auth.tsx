"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, store } from "./api";

export type Prop = { id: number; name: string; name_bn: string; city: string; org_id: number; org_name: string; roles: string[] };
export type Me = { id: number; name: string; name_bn: string; email: string; phone: string; lang: string; saas_role: string | null };
type AuthState = {
  ready: boolean; user: Me | null; properties: Prop[]; prop: Prop | null; roles: string[];
  setProp: (id: number) => void; login: (email: string, password: string) => Promise<void>; logout: () => void;
  has: (...r: string[]) => boolean; saas: (...r: string[]) => boolean; reload: () => Promise<void>;
};
const Ctx = createContext<AuthState>(null as unknown as AuthState);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<Me | null>(null);
  const [properties, setProps] = useState<Prop[]>([]);
  const [propId, setPropId] = useState(0);

  const apply = useCallback((d: { user: Me; properties: Prop[] }) => {
    setUser(d.user); setProps(d.properties);
    const saved = store.prop;
    const pick = d.properties.find((p) => p.id === saved) ?? d.properties[0];
    if (pick) { store.prop = pick.id; setPropId(pick.id); } else setPropId(0);
  }, []);

  const reload = useCallback(async () => {
    if (!store.token) { setReady(true); return; }
    try { apply(await api("/me")); } catch { store.token = ""; setUser(null); }
    setReady(true);
  }, [apply]);
  useEffect(() => { reload(); }, [reload]);

  const login = async (email: string, password: string) => {
    const d = await api("/auth/login", { body: { email, password } });
    store.token = d.token; apply(d); setReady(true);
  };
  const logout = () => { store.token = ""; setUser(null); setProps([]); setPropId(0); window.location.href = "/login"; };
  const setProp = (id: number) => { store.prop = id; setPropId(id); };
  const prop = properties.find((p) => p.id === propId) ?? null;
  const roles = prop?.roles ?? [];
  const value = useMemo<AuthState>(() => ({
    ready, user, properties, prop, roles, setProp, login, logout, reload,
    has: (...r) => r.some((x) => roles.includes(x)) || user?.saas_role === "SUPER_ADMIN" || user?.saas_role === "SAAS_ADMIN",
    saas: (...r) => !!user?.saas_role && (r.length === 0 || r.includes(user.saas_role)),
  }), [ready, user, properties, prop, roles, reload]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
export const useAuth = () => useContext(Ctx);
