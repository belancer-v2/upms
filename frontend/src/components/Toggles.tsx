"use client";
import { useT } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";

export function Toggles() {
  const { lang, setLang, t } = useT();
  const { theme, setTheme } = useTheme();
  return (
    <div className="row" style={{ gap: 8 }}>
      <div className="seg" role="group" aria-label={t("a11y.language")}>
        <button className={lang === "en" ? "on" : ""} onClick={() => setLang("en")}>{t("lang.en")}</button>
        <button className={lang === "bn" ? "on" : ""} onClick={() => setLang("bn")}>{t("lang.bn")}</button>
      </div>
      <button className="icon-btn" aria-label={theme === "dark" ? t("theme.light") : t("theme.dark")} title={theme === "dark" ? t("theme.light") : t("theme.dark")} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
        {theme === "dark"
          ? <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
          : <svg viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z" /></svg>}
      </button>
    </div>
  );
}
