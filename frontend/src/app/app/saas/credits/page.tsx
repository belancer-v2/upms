"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Pager } from "@/components/pager";
import { Btn, Card, Chip, Empty, Field, Modal, PageHead, Stat, Tabs, useToast } from "@/components/ui";
import { api, fdate, money } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type Sale = { id: number; org_id: number; org: string; by: string; kind: string; pack_name: string; pack_name_bn: string; credits: number; total: number; claimed_amount: number | null; method: string; status: string; trx_id: string; invoice_id: number | null; invoice: string; created_at: string; mismatch?: boolean; note: string };
type Page<R> = { total: number; rows: R[]; paid_total?: number };
type Pack = { id: number; kind: string; name: string; name_bn: string; credits: number; price: number; active: boolean; sort: number };
type Bal = { id: number; name: string; name_bn: string; city: string; sms: number; email: number; sms_low: number; email_low: number; low: boolean };
type Settings = { vat_bps: number; pay_bkash: string; pay_nagad: string; pay_bank: string };
const SIZE = 8;
const tone = (s: string) => (s === "paid" ? "ok" : s === "pending" ? "warn" : s === "rejected" || s === "failed" ? "bad" : "mute") as "ok" | "warn" | "bad" | "mute";

export default function SaasCredits() {
  const { t, pick } = useT(); const { saas } = useAuth(); const toast = useToast();
  const money_ok = saas("SUPER_ADMIN", "SAAS_ADMIN", "SAAS_FINANCE"); const [tab, setTab] = useState(money_ok ? "sales" : "balances");
  const tabs = [...(money_ok ? [{ id: "sales", label: t("cc.tab.sales") }, { id: "queue", label: t("cc.tab.queue") }] : []), { id: "packs", label: t("cc.tab.packs") }, { id: "balances", label: t("cc.tab.balances") }, ...(money_ok ? [{ id: "settings", label: t("cc.tab.settings") }] : [])];
  return (<>
    <PageHead title={t("cc.title")} sub={t("cc.sub")} />
    <div style={{ marginBottom: 16 }}><Tabs value={tab} onChange={setTab} items={tabs} /></div>
    {tab === "sales" && <Sales toast={toast} />}
    {tab === "queue" && <Queue toast={toast} />}
    {tab === "packs" && <Packs can={money_ok} toast={toast} pick={pick} />}
    {tab === "balances" && <Balances can={money_ok} toast={toast} />}
    {tab === "settings" && <SettingsTab toast={toast} />}
    {toast.node}</>);
}

function SalesTable({ rows, pick, t, actions }: { rows: Sale[]; pick: (a: string, b: string) => string; t: (k: string, v?: any) => string; actions?: (r: Sale) => React.ReactNode }) {
  return rows.length === 0 ? <Empty /> : <div className="table-wrap"><table className="t"><thead><tr><th>{t("cr.col.when")}</th><th>{t("cc.building")}</th><th>{t("cr.col.pack")}</th><th>{t("cr.col.method")}</th><th>{t("cr.col.trx")}</th><th className="num">{t("cr.col.total")}</th><th>{t("cr.col.status")}</th><th>{t("cr.col.invoice")}</th>{actions && <th />}</tr></thead><tbody>
    {rows.map((r) => <tr key={r.id}><td className="nowrap">{fdate(r.created_at)}</td><td>{r.org}</td><td>{pick(r.pack_name, r.pack_name_bn || r.pack_name)}</td><td>{t(`cr.m.${r.method}`)}</td><td>{r.trx_id}</td>
      <td className="num">{money(r.total)}{r.mismatch && <div className="small" style={{ color: "var(--bad)" }}>{t("cc.sent", { a: money(r.claimed_amount), b: money(r.total) })}</div>}</td>
      <td><Chip tone={tone(r.status)}>{t(`cr.st.${r.status}`)}</Chip></td><td>{r.invoice_id ? <Link href={`/app/credits/invoice/${r.invoice_id}`}>{r.invoice}</Link> : ""}</td>{actions && <td>{actions(r)}</td>}</tr>)}</tbody></table></div>;
}

function Sales({ toast }: { toast: ReturnType<typeof useToast> }) {
  const { t, pick } = useT(); void toast;
  const [d, setD] = useState<Page<Sale>>({ total: 0, rows: [] }); const [page, setPage] = useState(1); const [q, setQ] = useState(""); const [st, setSt] = useState(""); const [kind, setKind] = useState("");
  useEffect(() => { api<Page<Sale>>(`/saas/credits/sales?page=${page}&size=${SIZE}&q=${encodeURIComponent(q)}&status=${st}&kind=${kind}`).then(setD).catch(() => {}); }, [page, q, st, kind]);
  return <div className="stack">
    <div className="row wrap"><Card style={{ minWidth: 220 }}><Stat label={t("cc.revenue")} value={money(d.paid_total)} /></Card>
      <input className="input" style={{ maxWidth: 260 }} placeholder={t("common.search")} aria-label={t("common.search")} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
      <select className="input" style={{ maxWidth: 170 }} aria-label={t("cr.col.status")} value={st} onChange={(e) => { setSt(e.target.value); setPage(1); }}><option value="">{t("cc.all")}</option>{["paid", "pending", "rejected", "failed", "expired"].map((s) => <option key={s} value={s}>{t(`cr.st.${s}`)}</option>)}</select>
      <select className="input" style={{ maxWidth: 150 }} aria-label={t("cc.kind")} value={kind} onChange={(e) => { setKind(e.target.value); setPage(1); }}><option value="">{t("cc.all")}</option><option value="sms">{t("cr.sms")}</option><option value="email">{t("cr.email")}</option></select></div>
    <SalesTable rows={d.rows} pick={pick} t={t} /><Pager page={page} size={SIZE} total={d.total} onPage={setPage} /></div>;
}

function Queue({ toast }: { toast: ReturnType<typeof useToast> }) {
  const { t, pick } = useT(); const [d, setD] = useState<Page<Sale>>({ total: 0, rows: [] }); const [page, setPage] = useState(1); const [rej, setRej] = useState<Sale | null>(null); const [why, setWhy] = useState(""); const [err, setErr] = useState("");
  const load = useCallback(() => api<Page<Sale>>(`/saas/credits/queue?page=${page}&size=${SIZE}`).then(setD).catch(() => {}), [page]);
  useEffect(() => { load(); }, [load]);
  const verify = async (r: Sale) => { try { await api(`/saas/credits/purchases/${r.id}/verify`, { body: {} }); toast.show(t("cc.verified")); load(); } catch (e: any) { toast.show(e.message); } };
  const reject = async () => { if (!rej) return; try { await api(`/saas/credits/purchases/${rej.id}/reject`, { body: { reason: why } }); setRej(null); setWhy(""); toast.show(t("cc.rejected")); load(); } catch (e: any) { setErr(e.message); } };
  return <div className="stack">{d.rows.length === 0 ? <Empty>{t("cc.queue_none")}</Empty> : <SalesTable rows={d.rows} pick={pick} t={t} actions={(r) => <div className="row" style={{ gap: 6 }}><Btn size="sm" disabled={r.mismatch} onClick={() => verify(r)}>{t("cc.verify")}</Btn><Btn size="sm" variant="ghost" onClick={() => { setRej(r); setErr(""); }}>{t("cc.reject")}</Btn></div>} />}
    <Pager page={page} size={SIZE} total={d.total} onPage={setPage} />
    {rej && <Modal title={`${t("cc.reject")} · ${rej.org}`} onClose={() => setRej(null)}><Field label={t("cc.reject_reason")}><input className="input" value={why} onChange={(e) => setWhy(e.target.value)} /></Field>
      {err && <p className="error" role="alert">{err}</p>}<div className="row"><Btn variant="danger" disabled={why.trim().length < 3} onClick={reject}>{t("cc.reject")}</Btn><Btn variant="ghost" onClick={() => setRej(null)}>{t("common.cancel")}</Btn></div></Modal>}</div>;
}

function Packs({ can, toast, pick }: { can: boolean; toast: ReturnType<typeof useToast>; pick: (a: string, b: string) => string }) {
  const { t } = useT(); const [rows, setRows] = useState<Pack[]>([]); const [ed, setEd] = useState<(Omit<Pack, "id" | "price"> & { id?: number; price: string }) | null>(null); const [err, setErr] = useState("");
  const load = useCallback(() => api<Pack[]>("/saas/credits/packs").then(setRows), []);
  useEffect(() => { load(); }, [load]);
  const blank = { kind: "sms", name: "", name_bn: "", credits: 1000, price: "", active: true, sort: rows.length };
  const save = async () => {
    if (!ed) return; setErr("");
    const body = { kind: ed.kind, name: ed.name, name_bn: ed.name_bn, credits: Number(ed.credits), price: Math.round(parseFloat(ed.price || "0") * 100), active: ed.active, sort: Number(ed.sort) };
    try { await api(ed.id ? `/saas/credits/packs/${ed.id}` : "/saas/credits/packs", { method: ed. id ? "PUT" : "POST", body }); setEd(null); toast.show(t("cc.pack_saved")); load(); } catch (e: any) { setErr(e.message); }
  };
  return <div className="stack">{!can && <p className="small muted">{t("cc.pack_readonly")}</p>}
    {can && <div><Btn onClick={() => setEd(blank)}>{t("cc.pack_add")}</Btn></div>}
    {rows.length === 0 ? <Empty /> : <div className="table-wrap"><table className="t"><thead><tr><th>{t("cc.kind")}</th><th>{t("common.name")}</th><th className="num">{t("cc.pack_credits")}</th><th className="num">{t("cr.price")}</th><th>{t("common.status")}</th>{can && <th />}</tr></thead><tbody>
      {rows.map((p) => <tr key={p.id}><td>{t(`cr.${p.kind}`)}</td><td>{pick(p.name, p.name_bn || p.name)}</td><td className="num">{p.credits.toLocaleString("en-US")}</td><td className="num">{money(p.price)}</td>
        <td><Chip tone={p.active ? "ok" : "mute"}>{p.active ? t("cc.pack_active") : t("cc.off")}</Chip></td>{can && <td><Btn size="sm" variant="ghost" onClick={() => setEd({ ...p, price: (p.price / 100).toString() })}>{t("common.edit")}</Btn></td>}</tr>)}</tbody></table></div>}
    {ed && <Modal title={ed.id ? t("common.edit") : t("cc.pack_add")} onClose={() => setEd(null)}>
      <Field label={t("cc.kind")}><select className="input" value={ed.kind} onChange={(e) => setEd({ ...ed, kind: e.target.value })}><option value="sms">{t("cr.sms")}</option><option value="email">{t("cr.email")}</option></select></Field>
      <Field label={t("cc.pack_name")}><input className="input" value={ed.name} onChange={(e) => setEd({ ...ed, name: e.target.value })} /></Field>
      <Field label={t("cc.pack_name_bn")}><input className="input" value={ed.name_bn} onChange={(e) => setEd({ ...ed, name_bn: e.target.value })} /></Field>
      <Field label={t("cc.pack_credits")}><input className="input" type="number" min={1} value={ed.credits} onChange={(e) => setEd({ ...ed, credits: Number(e.target.value) })} /></Field>
      <Field label={t("cc.pack_price")}><input className="input" inputMode="decimal" value={ed.price} onChange={(e) => setEd({ ...ed, price: e.target.value })} /></Field>
      <label className="row" style={{ marginBottom: 12 }}><input type="checkbox" checked={ed.active} onChange={(e) => setEd({ ...ed, active: e.target.checked })} /> {t("cc.pack_active")}</label>
      {err && <p className="error" role="alert">{err}</p>}<div className="row"><Btn onClick={save}>{t("common.save")}</Btn><Btn variant="ghost" onClick={() => setEd(null)}>{t("common.cancel")}</Btn></div></Modal>}</div>;
}

function Balances({ can, toast }: { can: boolean; toast: ReturnType<typeof useToast> }) {
  const { t, pick } = useT(); const [d, setD] = useState<Page<Bal>>({ total: 0, rows: [] }); const [page, setPage] = useState(1); const [q, setQ] = useState(""); const [low, setLow] = useState(false);
  const [g, setG] = useState<Bal | null>(null); const [gk, setGk] = useState("sms"); const [gn, setGn] = useState("500"); const [gr, setGr] = useState(""); const [err, setErr] = useState("");
  const load = useCallback(() => api<Page<Bal>>(`/saas/credits/balances?page=${page}&size=${SIZE}&q=${encodeURIComponent(q)}&low=${low}`).then(setD).catch(() => {}), [page, q, low]);
  useEffect(() => { load(); }, [load]);
  const grant = async () => { if (!g) return; try { await api("/saas/credits/grant", { body: { org_id: g.id, kind: gk, credits: parseInt(gn, 10), reason: gr } }); setG(null); setGr(""); toast.show(t("cc.grant_done")); load(); } catch (e: any) { setErr(e.message); } };
  const n = (v: number, lo: number) => <span style={v < lo ? { color: "var(--bad)", fontWeight: 800 } : undefined}>{v.toLocaleString("en-US")}</span>;
  return <div className="stack">
    <div className="row wrap"><input className="input" style={{ maxWidth: 280 }} placeholder={t("cc.bal.search")} aria-label={t("cc.bal.search")} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
      <label className="row"><input type="checkbox" checked={low} onChange={(e) => { setLow(e.target.checked); setPage(1); }} /> {t("cc.bal.low_only")}</label></div>
    {d.rows.length === 0 ? <Empty /> : <div className="table-wrap"><table className="t"><thead><tr><th>{t("cc.building")}</th><th className="num">{t("cc.bal.sms")}</th><th className="num">{t("cc.bal.email")}</th><th /><th /></tr></thead><tbody>
      {d.rows.map((r) => <tr key={r.id}><td>{pick(r.name, r.name_bn || r.name)}<div className="small muted">{r.city}</div></td><td className="num">{n(r.sms, r.sms_low)}</td><td className="num">{n(r.email, r.email_low)}</td>
        <td>{r.low && <Chip tone="bad">{t("cc.bal.flag")}</Chip>}</td><td>{can && <Btn size="sm" variant="ghost" onClick={() => { setG(r); setErr(""); }}>{t("cc.grant")}</Btn>}</td></tr>)}</tbody></table></div>}
    <Pager page={page} size={SIZE} total={d.total} onPage={setPage} />
    {g && <Modal title={`${t("cc.grant")} · ${g.name}`} onClose={() => setG(null)}>
      <Field label={t("cc.kind")}><select className="input" value={gk} onChange={(e) => setGk(e.target.value)}><option value="sms">{t("cr.sms")}</option><option value="email">{t("cr.email")}</option></select></Field>
      <Field label={t("cc.pack_credits")}><input className="input" type="number" min={1} value={gn} onChange={(e) => setGn(e.target.value)} /></Field>
      <Field label={t("cc.grant_reason")}><input className="input" maxLength={50} value={gr} onChange={(e) => setGr(e.target.value)} /></Field>
      {err && <p className="error" role="alert">{err}</p>}<div className="row"><Btn disabled={gr.trim().length < 3} onClick={grant}>{t("cc.grant_go")}</Btn><Btn variant="ghost" onClick={() => setG(null)}>{t("common.cancel")}</Btn></div></Modal>}</div>;
}

function SettingsTab({ toast }: { toast: ReturnType<typeof useToast> }) {
  const { t } = useT(); const [s, setS] = useState<{ vat: string; pay_bkash: string; pay_nagad: string; pay_bank: string } | null>(null); const [err, setErr] = useState("");
  useEffect(() => { api<Settings>("/saas/credits/settings").then((d) => setS({ vat: String(d.vat_bps / 100), pay_bkash: d.pay_bkash, pay_nagad: d.pay_nagad, pay_bank: d.pay_bank })); }, []);
  if (!s) return <p className="muted">{t("common.loading")}</p>;
  const save = async () => { try { await api("/saas/credits/settings", { method: "PUT", body: { vat_bps: Math.round(parseFloat(s.vat || "0") * 100), pay_bkash: s.pay_bkash, pay_nagad: s.pay_nagad, pay_bank: s.pay_bank } }); setErr(""); toast.show(t("cc.settings_saved")); } catch (e: any) { setErr(e.message); } };
  return <Card className="stack" style={{ maxWidth: 520 }}>
    <Field label={t("cc.vat_pct")} hint={t("cc.vat_hint")}><input className="input" inputMode="decimal" value={s.vat} onChange={(e) => setS({ ...s, vat: e.target.value })} /></Field>
    <Field label={t("cc.pay_bkash")}><input className="input" value={s.pay_bkash} onChange={(e) => setS({ ...s, pay_bkash: e.target.value })} /></Field>
    <Field label={t("cc.pay_nagad")}><input className="input" value={s.pay_nagad} onChange={(e) => setS({ ...s, pay_nagad: e.target.value })} /></Field>
    <Field label={t("cc.pay_bank")}><input className="input" value={s.pay_bank} onChange={(e) => setS({ ...s, pay_bank: e.target.value })} /></Field>
    {err && <p className="error" role="alert">{err}</p>}<div><Btn onClick={save}>{t("common.save")}</Btn></div></Card>;
}
