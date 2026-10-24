"use client";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { dict } from "./dict";

export type Lang = "en" | "bn";
type Vars = Record<string, string | number>;
const Ctx = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: "en", setLang: () => {} });

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setL] = useState<Lang>("en");
  useEffect(() => {
    const saved = (localStorage.getItem("fw_lang") as Lang | null) ?? "en";
    setL(saved === "bn" ? "bn" : "en");
  }, []);
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  const setLang = useCallback((l: Lang) => {
    setL(l);
    localStorage.setItem("fw_lang", l);
    const token = localStorage.getItem("fw_token");
    if (token) fetch("/api/me/lang", { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ lang: l }) }).catch(() => {});
  }, []);
  return <Ctx.Provider value={{ lang, setLang }}>{children}</Ctx.Provider>;
}

export function useT() {
  const { lang, setLang } = useContext(Ctx);
  const t = (key: string, vars?: Vars) => {
    let s = dict[lang][key] ?? dict.en[key] ?? key;
    if (vars) for (const k of Object.keys(vars)) s = s.replaceAll(`{${k}}`, String(vars[k]));
    return s;
  };
  /** Pick the Bangla value when the interface is Bangla and one exists. */
  const pick = (en?: string | null, bn?: string | null) => (lang === "bn" && bn ? bn : en ?? "");
  return { t, lang, setLang, pick };
}
