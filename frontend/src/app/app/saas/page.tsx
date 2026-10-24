"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Bar, Card, Chip, PageHead, Stat } from "@/components/ui";
import { SubChip, daysLeft } from "@/components/saasbits";
import { api, fdate, money } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Ov = { buildings: Record<string, number>; flats: number; mrr: number | null; mrr_by_plan: Record<string, number> | null; overdue: { count: number; amount: number } | null; trials_ending: { id: number; name: string; trial_ends: string; plan: string }[]; leads: Record<string, number>; sms_low: { id: number; name: string; balance: number }[]; recent: { id: number; name: string; plan: string; status: string; created_at: string }[] };

export default function SaasOverview() {
  const { t } = useT(); const [d, setD] = useState<Ov | null>(null);
  useEffect(() => { api<Ov>("/saas/overview").then(setD); }, []);
  if (!d) return <p className="muted">{t("common.loading")}</p>;
  const maxPlan = Math.max(1, ...Object.values(d.mrr_by_plan ?? { x: 1 }));
  const maxLead = Math.max(1, ...Object.values(d.leads));
  return (
    <>
      <PageHead title={t("saas.over.title")} sub={t("saas.over.sub")} />
      <div className="grid g4">
        <Stat label={t("saas.stat.buildings")} value={d.buildings.total} note={`${d.flats} ${t("saas.stat.flats").toLowerCase()}`} />
        <Stat label={t("saas.stat.trial")} value={d.buildings.trial} note={`${d.trials_ending.length} · ${t("saas.over.trials").toLowerCase()}`} />
        <Stat label={t("saas.stat.active")} value={d.buildings.active + d.buildings.past_due} note={d.buildings.past_due ? `${d.buildings.past_due} ${t("sub.past_due").toLowerCase()}` : undefined} />
        {d.mrr !== null ? <Stat label={t("saas.stat.mrr")} value={money(d.mrr)} note={d.overdue ? `${t("saas.stat.overdue")}: ${d.overdue.count} · ${money(d.overdue.amount)}` : undefined} /> : <Stat label={t("saas.stat.leads")} value={d.leads.new} />}
      </div>
      <div className="grid g2" style={{ marginTop: 18 }}>
        {d.mrr_by_plan && <Card><h3>{t("saas.over.mrrplan")}</h3><div className="stack" style={{ marginTop: 14 }}>
          {Object.entries(d.mrr_by_plan).map(([k, v]) => <div key={k}><div className="row between small"><b style={{ textTransform: "capitalize" }}>{k}</b><span>{money(v)}</span></div><Bar pct={(v / maxPlan) * 100} /></div>)}</div></Card>}
        <Card><h3>{t("saas.over.pipeline")}</h3><div className="stack" style={{ marginTop: 14 }}>
          {["new", "contacted", "demo", "trial", "won", "lost"].map((k) => <div key={k}><div className="row between small"><b>{t(`lead.${k}`)}</b><span>{d.leads[k]}</span></div><Bar pct={(d.leads[k] / maxLead) * 100} spark={k === "won"} /></div>)}</div></Card>
        <Card><h3>{t("saas.over.trials")}</h3>
          {d.trials_ending.length === 0 ? <p className="muted">{t("saas.over.none")}</p> : <ul className="list-dot" style={{ marginTop: 10 }}>{d.trials_ending.map((x) => { const n = daysLeft(x.trial_ends); return <li key={x.id}><span><Link href={`/app/saas/buildings/${x.id}`}><b>{x.name}</b></Link> <Chip tone={n <= 2 ? "bad" : "warn"}>{n <= 0 ? t("saas.today") : t("saas.days_left", { n })}</Chip></span></li>; })}</ul>}
        </Card>
        <Card><h3>{t("saas.over.smslow")}</h3>
          {d.sms_low.length === 0 ? <p className="muted">{t("saas.over.none")}</p> : <ul className="list-dot" style={{ marginTop: 10 }}>{d.sms_low.map((x) => <li key={x.id}><span><Link href={`/app/saas/buildings/${x.id}`}><b>{x.name}</b></Link> <Chip tone="bad">{x.balance} SMS</Chip></span></li>)}</ul>}
        </Card>
        <Card style={{ gridColumn: "1 / -1" }}><h3>{t("saas.over.recent")}</h3>
          <ul className="list-dot" style={{ marginTop: 10 }}>{d.recent.map((x) => <li key={x.id}><span><Link href={`/app/saas/buildings/${x.id}`}><b>{x.name}</b></Link> · <span style={{ textTransform: "capitalize" }}>{x.plan}</span> <SubChip s={x.status} /> <span className="muted small">{fdate(x.created_at)}</span></span></li>)}</ul></Card>
      </div>
    </>
  );
}
