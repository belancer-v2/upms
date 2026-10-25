"use client";
import { useState, type ReactNode } from "react";
import { Card } from "@/components/ui";
import { Logo } from "@/components/Logo";
import { Toggles } from "@/components/Toggles";
import { useT } from "@/lib/i18n";

/** The centred card used by the account-security screens (forgot, reset and change password, e-mail confirmation). */
export function AuthShell({ title, sub, children }: { title: string; sub?: string; children: ReactNode }) {
  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: "24px 16px" }}>
      <div style={{ width: "100%", maxWidth: 480 }}>
        <div className="row between" style={{ marginBottom: 24 }}><Logo /><Toggles /></div>
        <Card>
          <h1 style={{ marginBottom: 6 }}>{title}</h1>
          {sub && <p className="muted" style={{ margin: "0 0 18px" }}>{sub}</p>}
          {children}
        </Card>
      </div>
    </div>
  );
}

/** A password input with a show/hide switch. Never autofilled with the old password. */
export function PasswordField({ value, onChange, autoComplete = "new-password", id, minLength = 8 }: { value: string; onChange: (v: string) => void; autoComplete?: string; id?: string; minLength?: number }) {
  const { t } = useT(); const [show, setShow] = useState(false);
  return (
    <div style={{ position: "relative" }}>
      <input id={id} className="input" type={show ? "text" : "password"} autoComplete={autoComplete} minLength={minLength} maxLength={72} required value={value} onChange={(e) => onChange(e.target.value)} style={{ paddingRight: 72 }} />
      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShow(!show)} style={{ position: "absolute", right: 4, top: 4 }} aria-pressed={show}>{show ? t("authx.hide") : t("authx.show")}</button>
    </div>
  );
}
