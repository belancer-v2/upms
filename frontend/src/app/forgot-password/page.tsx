"use client";
import Link from "next/link";
import { useState } from "react";
import { AuthShell } from "@/components/AuthShell";
import { Btn, Field } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function Forgot() {
  const { t } = useT();
  const [ident, setIdent] = useState(""); const [busy, setBusy] = useState(false); const [done, setDone] = useState(false); const [err, setErr] = useState(""); const [demo, setDemo] = useState("");
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr("");
    try { const r = await api<{ demo_link?: string }>("/auth/forgot-password", { body: { identifier: ident.trim() } }); setDemo(r.demo_link ?? ""); setDone(true); }
    catch (x) { setErr((x as ApiError).status === 429 ? t("authx.locked") : t("authx.forgot.err")); } finally { setBusy(false); }
  };
  return (
    <AuthShell title={t("authx.forgot.title")} sub={t("authx.forgot.sub")}>
      {done ? (
        <div className="stack">
          <p role="status">{t("authx.forgot.sent")}</p>
          {demo && <p className="hint">{t("authx.forgot.demo")}: <a href={demo.replace(/^https?:\/\/[^/]+/, "")}>{t("authx.reset.title")}</a></p>}
          <Link href="/login" className="btn btn-soft">{t("authx.back_login")}</Link>
        </div>
      ) : (
        <form onSubmit={submit}>
          <Field label={t("authx.forgot.ident")}><input className="input" autoComplete="username" required maxLength={160} value={ident} onChange={(e) => setIdent(e.target.value)} /></Field>
          {err && <p className="error" role="alert">{err}</p>}
          <Btn type="submit" size="lg" disabled={busy} style={{ width: "100%" }}>{t("authx.forgot.send")}</Btn>
          <p style={{ marginTop: 14 }}><Link href="/login">{t("authx.back_login")}</Link></p>
        </form>
      )}
    </AuthShell>
  );
}
