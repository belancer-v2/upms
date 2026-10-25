"use client";
import { useEffect, useRef, useState } from "react";
import { useT } from "./i18n";

/**
 * Anti-spam for the public forms, with no puzzle for the visitor: a signed form token fetched when the form opens (the server rejects
 * submissions that arrive within a few seconds of it) and a honeypot field that people never see and bots fill in.
 */
export function useFormGuard() {
  const [ft, setFt] = useState(""); const [hp, setHp] = useState("");
  useEffect(() => { fetch("/api/public/form-token").then((r) => r.json()).then((j) => setFt(j.ft ?? "")).catch(() => {}); }, []);
  return { ft, hp, setHp, extra: { ft, hp } };
}

export function Honeypot({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t } = useT(); const ref = useRef<HTMLInputElement>(null);
  return (
    <div aria-hidden="true" style={{ position: "absolute", left: -10000, top: "auto", width: 1, height: 1, overflow: "hidden" }}>
      <label>{t("authx.hp")}<input ref={ref} name="website" tabIndex={-1} autoComplete="off" value={value} onChange={(e) => onChange(e.target.value)} /></label>
    </div>
  );
}
