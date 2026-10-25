"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AuthShell } from "@/components/AuthShell";
import { Btn, Field } from "@/components/ui";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function VerifyEmail() {
  const { t } = useT();
  const [state, setState] = useState<"working" | "done" | "bad">("working");
  const [email, setEmail] = useState(""); const [sent, setSent] = useState(false); const [demo, setDemo] = useState("");
  useEffect(() => {
    const tok = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("token") || new URLSearchParams(window.location.search).get("token") || "";
    if (tok) window.history.replaceState(null, "", window.location.pathname);
    if (!tok) { setState("bad"); return; }
    api("/auth/verify-email", { body: { token: tok } }).then(() => setState("done")).catch(() => setState("bad"));
  }, []);
  const resend = async (e: React.FormEvent) => {
    e.preventDefault();
    try { const r = await api<{ demo_link?: string }>("/auth/resend-verification", { body: { email: email.trim() } }); setDemo(r.demo_link ?? ""); } catch { /* the answer is the same either way */ }
    setSent(true);
  };
  return (
    <AuthShell title={t("authx.verify.title")}>
      {state === "working" && <p role="status">{t("authx.verify.working")}</p>}
      {state === "done" && <div className="stack"><p role="status">{t("authx.verify.done")}</p><Link href="/login" className="btn btn-primary">{t("authx.verify.signin")}</Link></div>}
      {state === "bad" && (sent
        ? <div className="stack"><p role="status">{t("authx.verify.resent")}</p>{demo && <p className="hint">{t("authx.signup.demo")}: <a href={demo.replace(/^https?:\/\/[^/]+/, "")}>{t("authx.verify.title")}</a></p>}</div>
        : <form onSubmit={resend}><p className="error" role="alert" style={{ marginBottom: 12 }}>{t("authx.verify.invalid")}</p>
            <Field label={t("auth.email")}><input className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
            <Btn type="submit" size="lg" style={{ width: "100%" }}>{t("authx.verify.resend")}</Btn></form>)}
    </AuthShell>
  );
}
