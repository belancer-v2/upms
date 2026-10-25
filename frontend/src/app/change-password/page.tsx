"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthShell, PasswordField } from "@/components/AuthShell";
import { Btn, Field } from "@/components/ui";
import { ApiError, api, store } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

/** Also the forced screen: a person who signed in with a temporary password can reach nothing else until this is done. */
export default function ChangePassword() {
  const { t } = useT(); const router = useRouter(); const { ready, user, reload, logout } = useAuth();
  const [cur, setCur] = useState(""); const [a, setA] = useState(""); const [b, setB] = useState("");
  const [busy, setBusy] = useState(false); const [err, setErr] = useState(""); const [done, setDone] = useState(false);
  useEffect(() => { if (ready && !user) router.replace("/login"); }, [ready, user, router]);
  const forced = !!user?.must_change_password;
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr("");
    if (a !== b) { setErr(t("authx.change.mismatch")); return; }
    setBusy(true);
    try {
      const r = await api<{ token: string }>("/auth/change-password", { body: { current_password: cur, new_password: a } });
      store.token = r.token; await reload(); setDone(true);
      window.setTimeout(() => router.replace("/app"), forced ? 400 : 1200);
    } catch (x) { const s = (x as ApiError).status; setErr(s === 400 ? t("authx.change.wrong") : s === 429 ? t("authx.locked") : (x as ApiError).message); } finally { setBusy(false); }
  };
  if (!ready || !user) return <div className="empty" style={{ paddingTop: 120 }}>{t("common.loading")}</div>;
  return (
    <AuthShell title={t("authx.change.title")} sub={forced ? t("authx.change.first") : t("authx.pw_hint")}>
      {done ? <p role="status">{t("authx.change.done")}</p> : (
        <form onSubmit={submit}>
          <Field label={t("authx.change.current")}><PasswordField value={cur} onChange={setCur} autoComplete="current-password" minLength={1} /></Field>
          <Field label={t("authx.change.new")} hint={forced ? t("authx.pw_hint") : undefined}><PasswordField value={a} onChange={setA} /></Field>
          <Field label={t("authx.change.again")}><PasswordField value={b} onChange={setB} /></Field>
          {err && <p className="error" role="alert">{err}</p>}
          <Btn type="submit" size="lg" disabled={busy} style={{ width: "100%" }}>{t("authx.change.submit")}</Btn>
          <div className="row between" style={{ marginTop: 14 }}>
            {forced ? <span /> : <Link href="/app/profile">{t("common.back")}</Link>}
            {forced && <button type="button" className="btn btn-ghost btn-sm" onClick={logout}>{t("auth.signout")}</button>}
          </div>
        </form>
      )}
    </AuthShell>
  );
}
