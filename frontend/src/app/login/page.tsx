"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Logo } from "@/components/Logo";
import { Toggles } from "@/components/Toggles";
import { Btn, Field } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import { ALL_SAAS } from "@/lib/nav";

type Demo = { enabled: boolean; password: string; accounts: { email: string; name: string; name_bn: string; roles: string[] }[] };

export default function Login() {
  const { t, pick } = useT(); const { login, user, ready } = useAuth(); const router = useRouter();
  const [email, setEmail] = useState(""); const [pw, setPw] = useState(""); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const [demo, setDemo] = useState<Demo | null>(null);
  useEffect(() => { api<Demo>("/auth/demo-accounts").then(setDemo).catch(() => {}); }, []);
  useEffect(() => { if (ready && user) router.replace("/app"); }, [ready, user, router]);

  const go = async (e: string, p: string) => {
    setBusy(true); setErr("");
    try { await login(e, p); router.push("/app"); } catch { setErr(t("auth.wrong")); } finally { setBusy(false); }
  };
  const groups = demo?.enabled ? [
    { title: t("auth.demo_saas"), rows: demo.accounts.filter((a) => a.roles.some((r) => ALL_SAAS.includes(r))) },
    { title: t("auth.demo_agency"), rows: demo.accounts.filter((a) => a.roles.includes("AGENCY_MANAGER")) },
    { title: t("auth.demo_building"), rows: demo.accounts.filter((a) => !a.roles.some((r) => ALL_SAAS.includes(r) || r === "AGENCY_MANAGER")) },
  ] : [];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1.1fr)", minHeight: "100vh" }} className="login-grid">
      <div className="card-hero" style={{ padding: "48px 56px", display: "flex", flexDirection: "column", justifyContent: "space-between", position: "relative", overflow: "hidden" }}>
        <svg viewBox="0 0 700 600" style={{ position: "absolute", right: -160, top: 40, width: 900, opacity: .55 }} aria-hidden>
          <g fill="none" strokeLinejoin="round" strokeLinecap="round">
            <polyline points="-100,640 360,60 820,640" stroke="rgba(255,255,255,.07)" strokeWidth="240" />
            <polyline points="60,640 360,230 660,640" stroke="rgba(255,255,255,.10)" strokeWidth="170" />
            <polyline points="200,640 360,430 520,640" stroke="rgba(255,255,255,.15)" strokeWidth="100" />
          </g>
        </svg>
        <img src="/brand/logo-white.svg" alt="FlatWise" style={{ height: 38, width: "auto", position: "relative" }} />
        <div style={{ position: "relative" }}>
          <h1 style={{ fontSize: 58, color: "#fff", fontWeight: 900, letterSpacing: "-.04em" }}>{t("app.tagline").replace(/\.$/, "")}<span style={{ background: "var(--spark)", WebkitBackgroundClip: "text", color: "transparent" }}>.</span></h1>
          <p style={{ color: "#F1B8D3", fontSize: 20, marginTop: 14 }}>{t("auth.sub")}</p>
        </div>
        <span className="small" style={{ color: "#F1B8D3", position: "relative" }}>FlatWise · 2026</span>
      </div>
      <div style={{ padding: "28px 48px", overflowY: "auto" }}>
        <div className="row" style={{ justifyContent: "flex-end", marginBottom: 20 }}><Toggles /></div>
        <div style={{ maxWidth: 520, margin: "0 auto" }}>
          <div className="show-sm" style={{ marginBottom: 18 }}><Logo /></div>
          <h1>{t("auth.welcome")}</h1>
          <p className="muted" style={{ margin: "8px 0 22px" }}>{t("auth.sub")}</p>
          <form onSubmit={(e) => { e.preventDefault(); go(email, pw); }}>
            <Field label={t("auth.email")}><input className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></Field>
            <Field label={t("auth.password")}><input className="input" type="password" autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} required /></Field>
            {err && <p className="error" role="alert">{err}</p>}
            <Btn type="submit" size="lg" disabled={busy} style={{ width: "100%" }}>{t("auth.signin")}</Btn>
          </form>
          {demo?.enabled && (
            <div style={{ marginTop: 30 }}>
              <h3>{t("auth.demo")}</h3>
              <p className="hint" style={{ marginBottom: 10 }}>{t("auth.demo_hint", { pw: demo.password })}</p>
              {groups.map((g) => g.rows.length > 0 && (
                <div key={g.title} style={{ marginBottom: 14 }}>
                  <div className="eyebrow" style={{ marginBottom: 6 }}>{g.title}</div>
                  <div className="row wrap" style={{ gap: 8 }}>
                    {g.rows.map((a) => (
                      <button key={a.email} className="btn btn-ghost btn-sm" disabled={busy} onClick={() => go(a.email, demo.password)} title={a.email}>
                        {t(`role.${a.roles[0]}`)}{a.roles.length > 1 ? " +" + (a.roles.length - 1) : ""}
                        <span className="muted" style={{ fontWeight: 600 }}>· {pick(a.name, a.name_bn).split(" ")[0]}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <style>{`.show-sm{display:none}@media(max-width:960px){.login-grid{grid-template-columns:1fr!important}.login-grid>div:first-child{display:none}.show-sm{display:block}}`}</style>
    </div>
  );
}
