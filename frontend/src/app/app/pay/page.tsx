"use client";
import { useCallback, useEffect, useState } from "react";
import { BillChip, type Inv } from "@/components/billbits";
import { PayForm } from "@/components/PayForm";
import { Btn, Card, Empty, PageHead, Stat, useToast } from "@/components/ui";
import { api, fdate, money } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

export default function Pay() {
  const { t, pick } = useT(); const { prop } = useAuth(); const toast = useToast();
  const [rows, setRows] = useState<Inv[] | null>(null); const [open, setOpen] = useState<Inv | null>(null); const [cash, setCash] = useState<{ id: number; unit: string; amount: number; status: string }[]>([]); const [detail, setDetail] = useState<Record<number, Inv>>({});
  const load = useCallback(async () => { const r = await api<Inv[]>("/billing/invoices"); setRows(r); const d: Record<number, Inv> = {}; for (const i of r.slice(0, 6)) d[i.id] = await api(`/billing/invoices/${i.id}`); setDetail(d); try { setCash((await api<any[]>("/cash/entries")).filter((e) => e.status === "pending")); } catch { setCash([]); } }, []);
  useEffect(() => { load(); }, [load, prop?.id]);
  if (!rows) return <p className="muted">{t("common.loading")}</p>;
  const owed = rows.filter((r) => r.status !== "paid" && r.status !== "void").reduce((a, r) => a + r.balance, 0);
  return (<>
    <PageHead title={t("pay.title")} sub={t("pay.sub")} />
    <div className="grid g3" style={{ marginBottom: 16 }}><Stat label={t("bill.outstanding")} value={money(owed)} /><Stat label={t("bill.tab.invoices")} value={rows.length} /></div>
    {cash.map((e) => (<Card key={e.id} style={{ marginBottom: 12, borderColor: "var(--warn)" }}><div className="row between wrap"><div><h3 style={{ margin: 0 }}>{t("cash.payer_title")} · {e.unit}</h3><p className="small muted" style={{ margin: "4px 0 0" }}>{t("cash.payer_note", { a: money(e.amount) })}</p></div>
      <Btn onClick={async () => { await api(`/cash/entries/${e.id}/confirm`, { method: "POST" }); toast.show(t("cash.confirmed")); load(); }}>{t("cash.payer_confirm")}</Btn></div></Card>))}
    {rows.length === 0 && <Card><Empty>{t("pay.none")}</Empty></Card>}
    <div className="stack">{rows.slice(0, 6).map((i) => { const d = detail[i.id]; return (
      <Card key={i.id}><div className="row between wrap"><div><h3 style={{ margin: 0 }}>{i.period} · {i.unit}</h3><span className="small muted">{t("bill.due")} {fdate(i.due_date)}</span></div>
        <div className="row"><BillChip s={i.status} /><b>{money(i.total)}</b>{i.status !== "paid" && i.status !== "void" && <Btn size="sm" onClick={() => setOpen(i)}>{t("pay.i_paid")}</Btn>}</div></div>
        {d?.lines && <div style={{ marginTop: 10 }}>{d.lines.map((l, k) => <div key={k} className="row between small" style={{ padding: "4px 0", borderTop: "1px solid var(--line)" }}><span>{pick(l.description, l.description_bn || l.description)}</span><span>{money(l.amount)}</span></div>)}
          {d.payments?.map((p) => <div key={p.id} className="row between small" style={{ padding: "4px 0" }}><span>{fdate(p.paid_on)} · {t(`bill.m.${p.method}`)} <BillChip s={p.status} /></span>
            <span>{money(p.amount)} {p.status === "verified" && <a href={`/app/receipt/${p.id}`}>{t("bill.receipt")}</a>}</span></div>)}</div>}</Card>); })}</div>
    {open && <PayForm inv={open} staff={false} onClose={() => setOpen(null)} onDone={() => { setOpen(null); toast.show(t("bill.submitted")); load(); }} />}
    {toast.node}
  </>);
}
