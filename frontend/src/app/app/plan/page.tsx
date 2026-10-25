"use client";
import { useCallback, useEffect, useState } from "react";
import { Btn, Card, Chip, Field, Modal, PageHead, Stat, useToast } from "@/components/ui";
import { SubChip } from "@/components/saasbits";
import { authHeaders } from "@/components/Avatar";
import { api, fdate } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type Req = { id: number; status: string; reason: string; created_at: string; decision_note: string; decided_at: string | null };
type Plan = { plan: string; plan_name: string; plan_name_bn: string; band: string; cycle: string; status: string; flats: number; trial_ends: string | null; features: string[]; request: Req | null; grace_days: number;
  cancelled: { ended_at: string; readonly_from: string; readonly: boolean; days_left: number } | null };

export default function PlanPage() {
  const { t, pick } = useT(); const { prop } = useAuth(); const toast = useToast();
  const [d, setD] = useState<Plan | null>(null); const [ask, setAsk] = useState(false); const [why, setWhy] = useState(""); const [err, setErr] = useState("");
  const load = useCallback(() => api<Plan>("/plan").then(setD).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load, prop?.id]);
  const send = async () => { try { await api("/plan/cancel-request", { body: { reason: why } }); setAsk(false); setWhy(""); toast.show(t("cancel.sent")); load(); } catch (e: any) { toast.show(e.message); } };
  const withdraw = async () => { try { await api("/plan/cancel-request", { method: "DELETE" }); toast.show(t("cancel.withdrawn")); load(); } catch (e: any) { toast.show(e.message); } };
  const download = async () => {
    const r = await fetch("/api/plan/export", { headers: authHeaders() });
    if (!r.ok) return toast.show(r.statusText);
    const a = document.createElement("a"); a.href = URL.createObjectURL(await r.blob()); a.download = "flatwise-export.zip"; a.click();
  };
  if (err) return <p className="error" role="alert">{err}</p>;
  if (!d) return <p className="muted">{t("common.loading")}</p>;
  const pending = d.request?.status === "pending";
  return (<>
    <PageHead title={t("plan.title")} sub={t("plan.sub")} actions={<Btn variant="soft" onClick={download}>{t("plan.export")}</Btn>} />
    {d.cancelled && <Card style={{ marginBottom: 16, borderColor: d.cancelled.readonly ? "var(--bad)" : "var(--warn)" }}>
      <b>{d.cancelled.readonly ? t("plan.ended_ro") : t("plan.ended_grace", { n: d.cancelled.days_left })}</b>
      <p className="small muted" style={{ margin: "6px 0 0" }}>{t("plan.ended_on", { d: fdate(d.cancelled.ended_at) })} · {t("plan.ro_from", { d: fdate(d.cancelled.readonly_from) })} {t("plan.export_hint")}</p></Card>}
    <div className="grid g3">
      <Stat label={t("saas.b.plan")} value={pick(d.plan_name, d.plan_name_bn || d.plan_name)} note={<SubChip s={d.status} />} />
      <Stat label={t("saas.d.band")} value={d.band} note={t("plan.flats", { n: d.flats })} />
      <Stat label={t("saas.d.cycle")} value={t(`saas.d.cycle.${d.cycle || "monthly"}`)} note={d.status === "trial" && d.trial_ends ? `${t("saas.b.trial_ends")}: ${fdate(d.trial_ends)}` : undefined} />
    </div>
    <Card style={{ marginTop: 16 }}><h3 style={{ marginTop: 0 }}>{t("plan.features")}</h3>
      <div className="row wrap" style={{ gap: 8 }}>{d.features.length ? d.features.map((f) => <Chip key={f} tone="ok">{t(`feat.${f}`)}</Chip>) : <span className="muted">{t("common.none")}</span>}</div></Card>
    {d.status !== "cancelled" && <Card style={{ marginTop: 16 }}><h3 style={{ marginTop: 0 }}>{t("plan.cancel_title")}</h3><p className="small muted">{t("cancel.policy")}</p>
      {pending ? <div className="row between wrap"><span><Chip tone="warn">{t("cancel.pending")}</Chip> <span className="small muted">{fdate(d.request!.created_at)} · {d.request!.reason}</span></span><Btn variant="ghost" onClick={withdraw}>{t("cancel.withdraw")}</Btn></div>
        : <>{d.request?.status === "rejected" && <p className="small"><Chip tone="mute">{t("cancel.rejected")}</Chip> {d.request.decision_note}</p>}<Btn variant="outline" onClick={() => setAsk(true)}>{t("cancel.request")}</Btn></>}</Card>}
    {ask && <Modal title={t("cancel.request")} onClose={() => setAsk(false)}>
      <p className="small muted">{t("cancel.policy")}</p>
      <Field label={t("cancel.reason")}><textarea className="input" rows={3} value={why} onChange={(e) => setWhy(e.target.value)} /></Field>
      <div className="row"><Btn variant="danger" disabled={why.trim().length < 3} onClick={send}>{t("cancel.send")}</Btn><Btn variant="ghost" onClick={() => setAsk(false)}>{t("common.cancel")}</Btn></div></Modal>}
    {toast.node}
  </>);
}
