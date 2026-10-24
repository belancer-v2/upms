"use client";
import { use, useEffect, useState } from "react";
import { Logo } from "@/components/Logo";
import { Toggles } from "@/components/Toggles";
import { Btn, Chip } from "@/components/ui";
import { api, money } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Payload = { status: string; trx_id: string; amount: number; sig: string };
type S = { status: string; provider: string; invoice: string; period: string; unit: string; building: string; building_bn: string; charged: number; amount: number; fee: number; pay: Payload; fail: Payload };

/** Practice checkout. Stands in for the hosted page of bKash, Nagad or the card gateway. It posts the same signed callback a real provider would. */
export default function Sandbox({ params }: { params: Promise<{ session: string }> }) {
  const { session } = use(params); const { t, pick } = useT();
  const [s, setS] = useState<S | null>(null); const [gone, setGone] = useState(false); const [done, setDone] = useState<"" | "paid" | "failed">(""); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { api<S>(`/gateway/sandbox/${session}`).then((d) => { setS(d); if (d.status === "paid") setDone("paid"); else if (d.status !== "created") setDone("failed"); }).catch(() => setGone(true)); }, [session]);
  const send = async (p: Payload) => {
    setBusy(true); setErr("");
    try { const r = await api<{ status: "paid" | "failed" }>(`/gateway/callback/${session}`, { body: { status: p.status, trx_id: p.trx_id, amount: p.amount, sig: p.sig } }); setDone(r.status); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (<div style={{ maxWidth: 480, margin: "0 auto", padding: "20px 16px 60px" }}>
    <div className="row between" style={{ marginBottom: 24 }}><Logo /><Toggles /></div>
    {gone && <div className="card"><p>{t("gw.sb.gone")}</p></div>}
    {s && <div className="card stack">
      <div className="row between"><div className="eyebrow">{t("gw.sb.title")}</div><Chip tone="warn">{t(`gw.p.${s.provider}`)}</Chip></div>
      <div><span className="small muted">{t("gw.sb.to")} · {pick(s.building, s.building_bn || s.building)}</span><h1 style={{ margin: "4px 0", fontSize: 30 }}>{money(s.charged)}</h1>
        <span className="small muted">{s.unit} · {s.period} · {s.invoice}</span>{s.fee > 0 && s.charged > s.amount && <div className="small muted">{t("gw.fee_line", { f: money(s.fee) })}</div>}</div>
      {!done && <><p className="hint">{t("gw.sb.note")}</p>
        <div className="row"><Btn onClick={() => send(s.pay)} disabled={busy}>{t("gw.sb.pay")}</Btn><Btn variant="outline" onClick={() => send(s.fail)} disabled={busy}>{t("gw.sb.fail")}</Btn></div></>}
      {done && <><p role="status" style={{ fontWeight: 600, color: done === "paid" ? "var(--ok)" : "var(--bad)" }}>{done === "paid" ? t("gw.sb.paid") : t("gw.sb.failed")}</p><a className="btn btn-primary" href="/app/pay">{t("gw.sb.back")}</a></>}
      {err && <p className="error" role="alert">{err}</p>}</div>}
  </div>);
}
