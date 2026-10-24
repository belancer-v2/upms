"use client";
import { use, useEffect, useState } from "react";
import { Btn, Card, Chip } from "@/components/ui";
import { api, fdate, money } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Inv = { number: string; status: string; issued_at: string; paid_at: string | null; method: string; trx_id: string; items: { kind: string; name: string; name_bn: string; credits: number; amount: number }[];
  subtotal: number; vat_bps: number; vat: number; total: number; buyer: { name: string; name_bn: string; city: string }; seller: { name: string; city: string } };

/** Printable tax invoice and receipt for a credit purchase. */
export default function CreditInvoice({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params); const { t, pick } = useT(); const [i, setI] = useState<Inv | null>(null); const [err, setErr] = useState("");
  useEffect(() => { api<Inv>(`/credits/invoices/${id}`).then(setI).catch((e) => setErr(e.message)); }, [id]);
  if (err) return <p className="error">{err}</p>; if (!i) return <p className="muted">{t("common.loading")}</p>;
  const row = (k: string, v: React.ReactNode, bold = false) => <div className="row between" style={{ padding: "9px 0", borderTop: "1px solid var(--line)", fontWeight: bold ? 800 : 400 }}><span className={bold ? "" : "muted"}>{k}</span><span style={{ textAlign: "right" }}>{v}</span></div>;
  const chip = i.status === "paid" ? <Chip tone="ok">{t("cr.inv.paid")}</Chip> : i.status === "pending" ? <Chip tone="warn">{t("cr.inv.pending")}</Chip> : <Chip tone="mute">{t("cr.inv.void")}</Chip>;
  return (<div style={{ maxWidth: 640, margin: "0 auto" }}>
    <Card><div className="row between"><div><div className="eyebrow">{t("cr.inv.title")}</div><h2 style={{ margin: "4px 0" }}>{i.number}</h2><span className="small muted">{fdate(i.issued_at)}</span></div>{chip}</div>
      <div className="grid g2" style={{ margin: "18px 0" }}>
        <div><div className="small muted">{t("cr.inv.from")}</div><b>{i.seller.name}</b><div className="small">{i.seller.city}</div></div>
        <div><div className="small muted">{t("cr.inv.to")}</div><b>{pick(i.buyer.name, i.buyer.name_bn || i.buyer.name)}</b><div className="small">{i.buyer.city}</div></div></div>
      <div className="row between small muted" style={{ paddingBottom: 6 }}><span>{t("cr.inv.item")}</span><span>{t("common.amount")}</span></div>
      {i.items.map((it, n) => <div key={n} className="row between" style={{ padding: "9px 0", borderTop: "1px solid var(--line)" }}><span>{pick(it.name, it.name_bn || it.name)} · {t("cr.credits", { n: it.credits.toLocaleString("en-US") })}</span><span>{money(it.amount)}</span></div>)}
      {row(t("cr.inv.subtotal"), money(i.subtotal))}
      {i.vat_bps > 0 && row(t("cr.inv.vat", { p: `${(i.vat_bps / 100).toLocaleString("en-US", { maximumFractionDigits: 2 })}%` }), money(i.vat))}
      {row(t("cr.inv.total"), money(i.total), true)}
      {i.method && row(t("cr.inv.via"), `${t(`cr.m.${i.method}`)}${i.trx_id ? ` · ${i.trx_id}` : ""}`)}
      {i.paid_at && row(t("cr.inv.date"), fdate(i.paid_at))}
      <div className="row no-print" style={{ marginTop: 18 }}><Btn onClick={() => window.print()}>{t("common.print")}</Btn></div></Card></div>);
}
