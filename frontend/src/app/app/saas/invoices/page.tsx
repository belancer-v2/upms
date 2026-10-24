"use client";
import { useCallback, useEffect, useState } from "react";
import { Btn, DataTable, Field, Modal, PageHead, Tabs, useToast } from "@/components/ui";
import { InvChip } from "@/components/saasbits";
import { api, fdate, money } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Inv = { id: number; number: string; org: string; org_id: number; kind: string; period: string; amount: number; status: string; due_at: string; paid_at: string | null; method: string };

export default function Invoices() {
  const { t } = useT(); const toast = useToast();
  const [rows, setRows] = useState<Inv[]>([]); const [f, setF] = useState("all"); const [pay, setPay] = useState<Inv | null>(null);
  const [m, setM] = useState("bkash"); const [trx, setTrx] = useState(""); const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const load = useCallback(() => api<Inv[]>("/saas/invoices").then(setRows), []);
  useEffect(() => { load(); }, [load]);
  const view = f === "all" ? rows : rows.filter((r) => r.status === f);
  const run = async () => { const r = await api("/saas/invoices/run", { body: { period } }); toast.show(t("saas.inv.created", { n: r.created, amt: (r.total / 100).toLocaleString("en-US") })); load(); };
  const doPay = async () => { if (!pay) return; await api(`/saas/invoices/${pay.id}/pay`, { body: { method: m, trx_id: trx } }); setPay(null); setTrx(""); load(); };
  return (
    <>
      <PageHead title={t("saas.inv.title")} sub={t("saas.inv.sub")} actions={<><input className="input" style={{ width: 150 }} type="month" value={period} onChange={(e) => setPeriod(e.target.value)} aria-label={t("saas.inv.period")} /><Btn onClick={run}>{t("saas.inv.run")}</Btn></>} />
      <div style={{ marginBottom: 16 }}><Tabs value={f} onChange={setF} items={[{ id: "all", label: `${t("common.all")} · ${rows.length}` }, ...["issued", "overdue", "paid"].map((s) => ({ id: s, label: `${t(`inv.${s}`)} · ${rows.filter((r) => r.status === s).length}` }))]} /></div>
      <DataTable rows={view} search={(r) => `${r.number} ${r.org}`} cols={[
        { key: "number", head: t("saas.inv.number"), render: (r) => <b>{r.number}</b> },
        { key: "org", head: t("saas.inv.customer") },
        { key: "kind", head: t("saas.inv.period"), render: (r) => `${t(`saas.inv.kind.${r.kind}`)} ${r.period}` },
        { key: "amount", head: t("common.amount"), num: true, render: (r) => money(r.amount) },
        { key: "due_at", head: t("saas.inv.due"), render: (r) => <span className="nowrap">{fdate(r.due_at)}</span> },
        { key: "status", head: t("common.status"), render: (r) => <InvChip s={r.status} /> },
        { key: "act", head: "", render: (r) => (r.status === "issued" || r.status === "overdue") ? <div className="row" style={{ gap: 6 }}><Btn size="sm" onClick={() => setPay(r)}>{t("saas.inv.pay")}</Btn><Btn size="sm" variant="ghost" onClick={async () => { await api(`/saas/invoices/${r.id}/void`, { body: {} }); load(); }}>{t("saas.inv.void")}</Btn></div> : r.paid_at ? <span className="small muted">{t("saas.inv.paid_on", { d: fdate(r.paid_at) })}</span> : null },
      ]} />
      {pay && <Modal title={`${t("saas.inv.pay")} · ${pay.number}`} onClose={() => setPay(null)}>
        <p className="muted">{pay.org} · <b>{money(pay.amount)}</b></p>
        <Field label={t("saas.inv.method")}><select className="input" value={m} onChange={(e) => setM(e.target.value)}><option value="bkash">bKash</option><option value="nagad">Nagad</option><option value="bank">Bank</option><option value="cash">Cash</option></select></Field>
        <Field label={t("saas.inv.trx")}><input className="input" value={trx} onChange={(e) => setTrx(e.target.value)} /></Field>
        <div className="row"><Btn onClick={doPay}>{t("saas.inv.pay")}</Btn><Btn variant="ghost" onClick={() => setPay(null)}>{t("common.cancel")}</Btn></div></Modal>}
      {toast.node}
    </>
  );
}
