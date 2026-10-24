"use client";
import { use, useEffect, useState } from "react";
import { Btn, Card } from "@/components/ui";
import { api, fdate, money } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type R = { receipt_no: string; paid_on: string; amount: number; method: string; trx_id: string; period: string; invoice: string; unit: string; balance_after: number; building: string; building_bn: string; address: string; people: { kind: string; name: string; name_bn: string }[]; received_by: string };
export default function Receipt({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params); const { t, pick } = useT(); const { prop } = useAuth(); const [r, setR] = useState<R | null>(null); const [err, setErr] = useState("");
  useEffect(() => { api<R>(`/billing/receipts/${id}`).then(setR).catch((e) => setErr(e.message)); }, [id, prop?.id]);
  if (err) return <p className="error">{err}</p>; if (!r) return <p className="muted">{t("common.loading")}</p>;
  const row = (k: string, v: React.ReactNode) => <div className="row between" style={{ padding: "9px 0", borderTop: "1px solid var(--line)" }}><span className="muted">{k}</span><b style={{ textAlign: "right" }}>{v}</b></div>;
  return (<div style={{ maxWidth: 560, margin: "0 auto" }}>
    <Card><div className="row between"><div><div className="eyebrow">{t("rc.title")}</div><h2 style={{ margin: "4px 0" }}>{pick(r.building, r.building_bn || r.building)}</h2><span className="small muted">{r.address}</span></div><b>{r.receipt_no}</b></div>
      <div style={{ margin: "22px 0 8px", fontSize: 34, fontWeight: 800 }}>{money(r.amount)}</div>
      {row(t("rc.received"), r.people.map((p) => pick(p.name, p.name_bn)).join(", ") + ` · ${r.unit}`)}{row(t("rc.for"), `${r.period} · ${r.invoice}`)}
      {row(t("rc.via"), t(`bill.m.${r.method}`) + (r.trx_id ? ` · ${r.trx_id}` : ""))}{row(t("common.date"), fdate(r.paid_on))}{row(t("rc.after"), money(r.balance_after))}{row(t("rc.by"), r.received_by)}
      <div className="row" style={{ marginTop: 18 }}><Btn onClick={() => window.print()}>{t("common.print")}</Btn></div></Card></div>);
}
