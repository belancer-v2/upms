"use client";
import Link from "next/link";
import { use, useEffect, useState } from "react";
import { Btn, Card } from "@/components/ui";
import { api, fdate, money } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type R = { receipt_no: string; paid_on: string; amount: number; method: string; bank_ref: string; period: string; note: string; unit: string; building: string; building_bn: string; address: string; month_due: number; month_outstanding: number; people: { kind: string; name: string; name_bn: string }[]; received_by: string };
export default function RentReceipt({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params); const { t, pick } = useT(); const { prop } = useAuth(); const [r, setR] = useState<R | null>(null); const [err, setErr] = useState("");
  useEffect(() => { api<R>(`/rental/payments/${id}/receipt`).then(setR).catch((e) => setErr(e.message)); }, [id, prop?.id]);
  if (err) return <p className="error">{err}</p>; if (!r) return <p className="muted">{t("common.loading")}</p>;
  const row = (k: string, v: React.ReactNode) => <div className="row between" style={{ padding: "9px 0", borderTop: "1px solid var(--line)" }}><span className="muted">{k}</span><b style={{ textAlign: "right" }}>{v}</b></div>;
  const tenant = r.people.filter((p) => p.kind === "tenant");
  return (<div style={{ maxWidth: 560, margin: "0 auto" }}>
    <Card><div className="row between"><div><div className="eyebrow">{t("rrc.title")}</div><h2 style={{ margin: "4px 0" }}>{pick(r.building, r.building_bn || r.building)} · {r.unit}</h2><span className="small muted">{r.address}</span></div><b>{r.receipt_no}</b></div>
      <div style={{ margin: "22px 0 8px", fontSize: 34, fontWeight: 800 }}>{money(r.amount)}</div>
      {row(t("rrc.received"), (tenant.length ? tenant : r.people).map((p) => pick(p.name, p.name_bn)).join(", "))}{row(t("rrc.for"), r.period)}
      {row(t("rrc.via"), t(`rent.m.${r.method}`))}{r.bank_ref && row(t("rrc.ref"), r.bank_ref)}{row(t("rrc.date"), fdate(r.paid_on))}
      {row(t("rrc.due"), money(r.month_due))}{row(t("rrc.left"), money(r.month_outstanding))}{r.received_by && row(t("rrc.by"), r.received_by)}
      <div className="row" style={{ marginTop: 18 }}><Btn onClick={() => window.print()}>{t("common.print")}</Btn><Link href="/app/rental" className="btn btn-ghost">{t("rrc.back")}</Link></div></Card></div>);
}
