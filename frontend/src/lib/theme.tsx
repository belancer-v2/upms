"use client";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

type Theme = "light" | "dark";
const Ctx = createContext<{ theme: Theme; setTheme: (t: Theme) => void }>({ theme: "light", setTheme: () => {} });

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setT] = useState<Theme>("light");
  useEffect(() => { setT((document.documentElement.dataset.theme as Theme) || "light"); }, []);
  const setTheme = (t: Theme) => {
    setT(t);
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem("fw_theme", t); } catch {}
  };
  return <Ctx.Provider value={{ theme, setTheme }}>{children}</Ctx.Provider>;
}
export const useTheme = () => useContext(Ctx);

/** Runs before first paint so there is no light flash in night mode. */
export const themeBootScript = `(function(){try{var t=localStorage.getItem('fw_theme');if(!t){t=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}document.documentElement.dataset.theme=t}catch(e){}})();`;
