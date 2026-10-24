"use client";
import { use, useEffect, useState } from "react";
import { Logo } from "@/components/Logo";
import { Toggles } from "@/components/Toggles";
import { Btn, Chip } from "@/components/ui";
import { api, money } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Payload = { status: string; trx_id: string; amount: number; sig: string };
type S = { status: string; method: string; pack_name: string; pack_name_bn: string; credits: number; total: number; vat: number; pay: Payload; fail: Payload };

/** Practice checkout for FlatWise's own merchant account. Posts the same signed callback a real provider would. */
export default function CreditsSandbox({ params }: { params: Promise<{ session: string }> }) {
  const { session } = use(params); const { t, pick } = useT();
  const [s, setS] = useState<S | null>(null); const [gone, setGone] = useState(false); const [done, setDone] = useState<"" | "paid" | "failed">(""); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { api<S>(`/credits/sandbox/${session}`).then((d) => { setS(d); if (d.status === "paid") setDone("paid"); else if (d.status !== "created") setDone("failed"); }).catch(() => setGone(true)); }, [session]);
  const send = async (p: Payload) => {
    setBusy(true); setErr("");
    try { const r = await api<{ status: "paid" | "failed" }>(`/credits/callback/${session}`, { body: { status: p.status, trx_id: p.trx_id, amount: p.amount, sig: p.sig } }); setDone(r.status); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (<div style={{ maxWidth: 480, margin: "0 auto", padding: "20px 16px 60px" }}>
    <div className="row between" style={{ marginBottom: 24 }}><Logo /><Toggles /></div>
    {gone && <div className="card"><p>{t("cr.sb.gone")}</p></div>}
    {s && <div className="card stack">
      <div className="row between"><div className="eyebrow">{t("cr.sb.title")}</div><Chip tone="warn">{t(`cr.m.${s.method}`)}</Chip></div>
      <div><span className="small muted">{t("cr.sb.to")}</span><h1 style={{ margin: "4px 0", fontSize: 30 }}>{money(s.total)}</h1>
        <span className="small muted">{pick(s.pack_name, s.pack_name_bn || s.pack_name)} · {t("cr.credits", { n: s.credits.toLocaleString("en-US") })}</span></div>
      {!done && <><p className="hint">{t("cr.sb.note")}</p>
        <div className="row"><Btn onClick={() => send(s.pay)} disabled={busy}>{t("cr.sb.pay")}</Btn><Btn variant="outline" onClick={() => send(s.fail)} disabled={busy}>{t("cr.sb.fail")}</Btn></div></>}
      {done && <><p role="status" style={{ fontWeight: 600, color: done === "paid" ? "var(--ok)" : "var(--bad)" }}>{done === "paid" ? t("cr.sb.paid") : t("cr.sb.failed")}</p><a className="btn btn-primary" href="/app/credits">{t("cr.sb.back")}</a></>}
      {err && <p className="error" role="alert">{err}</p>}</div>}
  </div>);
}
