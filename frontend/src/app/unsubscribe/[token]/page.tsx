"use client";
import { use, useEffect, useState } from "react";
import { Logo } from "@/components/Logo";
import { Toggles } from "@/components/Toggles";
import { Btn } from "@/components/ui";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

type State = "loading" | "invalid" | "ready" | "done";

/** Public page. No sign-in. GET only shows who the link is for; the button sends the POST. */
export default function Unsubscribe({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params); const { t } = useT();
  const [state, setState] = useState<State>("loading"); const [email, setEmail] = useState(""); const [already, setAlready] = useState(false); const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<{ email: string; already: boolean }>(`/public/unsubscribe/${token}`).then((d) => { setEmail(d.email); setAlready(d.already); setState(d.already ? "done" : "ready"); }).catch(() => setState("invalid"));
  }, [token]);
  const confirm = async () => {
    setBusy(true);
    try { const d = await api<{ email: string }>(`/public/unsubscribe/${token}`, { method: "POST", body: {} }); setEmail(d.email); setState("done"); } catch { setState("invalid"); } finally { setBusy(false); }
  };
  return (
    <div style={{ maxWidth: 560, margin: "0 auto", padding: "20px 16px 60px" }}>
      <div className="row between" style={{ marginBottom: 24 }}><Logo /><Toggles /></div>
      <div className="card" role="status" aria-live="polite">
        {state === "loading" && <p>{t("common.loading")}</p>}
        {state === "invalid" && <><h1 style={{ fontSize: 24, margin: "0 0 8px" }}>{t("mail.unsub.bad_title")}</h1><p>{t("mail.unsub.bad")}</p></>}
        {state === "ready" && <><div className="eyebrow">{t("mail.unsub.eyebrow")}</div><h1 style={{ fontSize: 26, margin: "8px 0" }}>{t("mail.unsub.title")}</h1>
          <p>{t("mail.unsub.ask", { e: email })}</p><p className="small muted">{t("mail.unsub.note")}</p><Btn onClick={confirm} disabled={busy}>{t("mail.unsub.confirm")}</Btn></>}
        {state === "done" && <><div className="eyebrow">{t("mail.unsub.eyebrow")}</div><h1 style={{ fontSize: 26, margin: "8px 0" }}>{already ? t("mail.unsub.already_title") : t("mail.unsub.done_title")}</h1>
          <p>{t("mail.unsub.done", { e: email })}</p><p className="small muted">{t("mail.unsub.note")}</p></>}
      </div>
    </div>
  );
}
