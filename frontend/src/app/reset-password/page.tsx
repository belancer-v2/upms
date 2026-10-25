"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AuthShell, PasswordField } from "@/components/AuthShell";
import { Btn, Field } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function Reset() {
  const { t } = useT();
  const [token, setToken] = useState(""); const [a, setA] = useState(""); const [b, setB] = useState("");
  const [busy, setBusy] = useState(false); const [done, setDone] = useState(false); const [err, setErr] = useState(""); const [bad, setBad] = useState(false);
  // The link carries the token after "#", which browsers never send to servers. Read it, then remove it from the address bar.
  useEffect(() => {
    const h = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("token") || new URLSearchParams(window.location.search).get("token") || "";
    setToken(h); setBad(!h);
    if (h) window.history.replaceState(null, "", window.location.pathname);
  }, []);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr("");
    if (a !== b) { setErr(t("authx.reset.mismatch")); return; }
    setBusy(true);
    try { await api("/auth/reset-password", { body: { token, new_password: a } }); setDone(true); }
    catch (x) { const s = (x as ApiError).status; if (s === 400) setBad(true); else setErr(s === 429 ? t("authx.locked") : (x as ApiError).message); } finally { setBusy(false); }
  };
  if (done) return <AuthShell title={t("authx.reset.title")}><p role="status">{t("authx.reset.done")}</p><Link href="/login" className="btn btn-primary" style={{ marginTop: 14 }}>{t("auth.signin")}</Link></AuthShell>;
  if (bad) return <AuthShell title={t("authx.reset.title")}><p className="error" role="alert">{t("authx.reset.invalid")}</p><Link href="/forgot-password" className="btn btn-soft" style={{ marginTop: 14 }}>{t("authx.reset.ask_again")}</Link></AuthShell>;
  return (
    <AuthShell title={t("authx.reset.title")} sub={t("authx.pw_hint")}>
      <form onSubmit={submit}>
        <Field label={t("authx.reset.new")}><PasswordField value={a} onChange={setA} /></Field>
        <Field label={t("authx.reset.again")}><PasswordField value={b} onChange={setB} /></Field>
        {err && <p className="error" role="alert">{err}</p>}
        <Btn type="submit" size="lg" disabled={busy || !token} style={{ width: "100%" }}>{t("authx.reset.submit")}</Btn>
      </form>
    </AuthShell>
  );
}
