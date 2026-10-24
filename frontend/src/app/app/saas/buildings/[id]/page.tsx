"use client";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Btn, Card, Chip, Field, PageHead, useToast } from "@/components/ui";
import { InvChip, SubChip, daysLeft } from "@/components/saasbits";
import { api, fdate, ftime, money } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type Feat = { key: string; plan: boolean; override: boolean | null; on: boolean };
type Detail = { id: number; name: string; name_bn: string; city: string; status: string; sub_status: string; plan: string; band: string; cycle: string; flats: number; discount_pct: number; trial_ends: string | null; mrr: number; sms_balance: number; users: number;
  buildings: { id: number; name: string; city: string; floors: number }[]; contacts: { name: string; email: string; role: string }[]; features: Feat[]; invoices: any[]; sms_ledger: { id: number; delta: number; reason: string; at: string }[] };

export default function BuildingDetail() {
  const { id } = useParams<{ id: string }>(); const { t, pick } = useT(); const { saas } = useAuth(); const toast = useToast();
  const [d, setD] = useState<Detail | null>(null); const [plan, setPlan] = useState({ plan: "standard", band: "M", cycle: "monthly", discount_pct: 0 }); const [sms, setSms] = useState(1000);
  const load = useCallback(async () => { const x = await api<Detail>(`/saas/orgs/${id}`); setD(x); setPlan({ plan: x.plan, band: x.band, cycle: x.cycle, discount_pct: x.discount_pct }); }, [id]);
  useEffect(() => { load(); }, [load]);
  if (!d) return <p className="muted">{t("common.loading")}</p>;
  const act = async (fn: () => Promise<any>) => { try { await fn(); await load(); toast.show(t("saas.toast.saved")); } catch (e: any) { toast.show(e.message); } };
  const admin = saas("SUPER_ADMIN", "SAAS_ADMIN"); const lead = saas("SUPER_ADMIN", "SAAS_ADMIN", "SAAS_SALES"); const money_ok = saas("SUPER_ADMIN", "SAAS_ADMIN", "SAAS_FINANCE");
  return (
    <>
      <PageHead eyebrow={t("saas.b.title")} title={pick(d.name, d.name_bn)} sub={`${d.city} · ${d.flats} ${t("saas.b.flats").toLowerCase()} · ${d.users} ${t("saas.b.users").toLowerCase()}`}
        actions={<><SubChip s={d.sub_status} />
          {admin && d.sub_status !== "active" && d.sub_status !== "suspended" && <Btn onClick={() => act(() => api(`/saas/orgs/${id}/status`, { body: { status: "active" } }))}>{t("saas.d.activate")}</Btn>}
          {admin && d.sub_status === "suspended" && <Btn onClick={() => act(() => api(`/saas/orgs/${id}/status`, { body: { status: "active" } }))}>{t("saas.d.activate")}</Btn>}
          {admin && d.sub_status !== "suspended" && <Btn variant="danger" onClick={() => act(() => api(`/saas/orgs/${id}/status`, { body: { status: "suspended" } }))}>{t("saas.d.suspend")}</Btn>}</>} />
      {d.sub_status === "suspended" && <Card style={{ marginBottom: 16, borderColor: "var(--bad)" }}><b style={{ color: "var(--bad)" }}>{t("saas.d.suspended_note")}</b></Card>}
      <div className="grid g2">
        <Card><h3>{t("saas.d.subscription")}</h3>
          <div className="grid g2" style={{ marginTop: 14 }}>
            <Field label={t("saas.b.plan")}><select className="input" disabled={!lead} value={plan.plan} onChange={(e) => setPlan({ ...plan, plan: e.target.value })}><option value="basic">Basic</option><option value="standard">Standard</option><option value="pro">Pro</option></select></Field>
            <Field label={t("saas.d.band")}><select className="input" disabled={!lead} value={plan.band} onChange={(e) => setPlan({ ...plan, band: e.target.value })}>{["S", "M", "L", "XL"].map((b) => <option key={b}>{b}</option>)}</select></Field>
            <Field label={t("saas.d.cycle")}><select className="input" disabled={!lead} value={plan.cycle} onChange={(e) => setPlan({ ...plan, cycle: e.target.value })}><option value="monthly">{t("saas.d.cycle.monthly")}</option><option value="yearly">{t("saas.d.cycle.yearly")}</option></select></Field>
            <Field label={t("saas.d.discount")}><input className="input" type="number" min={0} max={100} disabled={!lead} value={plan.discount_pct} onChange={(e) => setPlan({ ...plan, discount_pct: Number(e.target.value) })} /></Field>
          </div>
          <div className="row wrap">{lead && <Btn onClick={() => act(() => api(`/saas/orgs/${id}/plan`, { body: plan }))}>{t("saas.d.save_plan")}</Btn>}
            {d.sub_status === "trial" && lead && <Btn variant="soft" onClick={() => act(() => api(`/saas/orgs/${id}/trial`, { body: { days: 7 } }))}>{t("saas.d.extend")}</Btn>}</div>
          {d.sub_status === "trial" && d.trial_ends && <p className="small muted" style={{ marginTop: 12 }}>{t("saas.b.trial_ends")}: {fdate(d.trial_ends)} · {t("saas.days_left", { n: Math.max(0, daysLeft(d.trial_ends)) })}</p>}
          {money_ok && d.mrr > 0 && <p className="small muted">{t("saas.b.mrr")}: <b>{money(d.mrr)}</b></p>}
        </Card>
        <Card><h3>{t("saas.d.sms")}</h3><div className="stat" style={{ margin: "8px 0 12px" }}><span className="v" style={{ color: d.sms_balance < 100 ? "var(--bad)" : undefined }}>{d.sms_balance}</span></div>
          {money_ok && <div className="row wrap"><input className="input" style={{ width: 130 }} type="number" min={100} step={100} value={sms} onChange={(e) => setSms(Number(e.target.value))} aria-label={t("saas.d.count")} /><Btn variant="soft" onClick={() => act(() => api(`/saas/orgs/${id}/sms`, { body: { count: sms, reason: "SMS pack", bill: true } }))}>{t("saas.d.topup")}</Btn></div>}
          <ul className="list-dot" style={{ marginTop: 12 }}>{d.sms_ledger.slice(0, 5).map((l) => <li key={l.id}><span><b>{l.delta > 0 ? "+" : ""}{l.delta}</b> · {l.reason} <span className="muted small">· {ftime(l.at)}</span></span></li>)}</ul></Card>
        <Card style={{ gridColumn: "1 / -1" }}><h3>{t("saas.d.features")}</h3><p className="small muted">{t("saas.d.features_sub")}</p>
          <div className="row wrap" style={{ gap: 8, marginTop: 14 }}>{d.features.map((f) => (
            <button key={f.key} disabled={!admin} className={`chip ${f.on ? "ok" : "mute"}`} style={{ cursor: admin ? "pointer" : "default", border: "none", padding: "7px 13px" }} onClick={() => act(() => api(`/saas/orgs/${id}/features`, { method: "PUT", body: { key: f.key, enabled: !f.on } }))} title={f.override !== null ? t("saas.d.override") : t("saas.d.from_plan")}>
              {f.on ? "✓" : "–"} {t(`feat.${f.key}`)}{f.override !== null && " ★"}</button>))}</div></Card>
        {money_ok && <Card style={{ gridColumn: "1 / -1" }}><h3>{t("saas.d.invoices")}</h3>
          <div className="table-wrap" style={{ marginTop: 12 }}><table className="t"><thead><tr><th>{t("saas.inv.number")}</th><th>{t("saas.inv.period")}</th><th className="num">{t("common.amount")}</th><th>{t("common.status")}</th></tr></thead>
            <tbody>{d.invoices.map((i) => <tr key={i.id}><td>{i.number}</td><td>{t(`saas.inv.kind.${i.kind}`)} {i.period}</td><td className="num">{money(i.amount)}</td><td><InvChip s={i.status} /></td></tr>)}</tbody></table></div></Card>}
        <Card><h3>{t("saas.d.buildings")}</h3><ul className="list-dot" style={{ marginTop: 10 }}>{d.buildings.map((b) => <li key={b.id}><span><b>{b.name}</b> · {b.city}</span></li>)}</ul></Card>
        <Card><h3>{t("saas.d.contacts")}</h3><ul className="list-dot" style={{ marginTop: 10 }}>{d.contacts.map((c, i) => <li key={i}><span><b>{c.name}</b> · {t(`role.${c.role}`)}<br /><span className="muted small">{c.email}</span></span></li>)}</ul></Card>
      </div>
      {toast.node}
    </>
  );
}
