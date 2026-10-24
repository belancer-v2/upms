"use client";
import { useCallback, useEffect, useState } from "react";
import { Bar, Btn, Card, Chip, DataTable, Empty, Field, Modal, PageHead, Stat, Tabs, useToast } from "@/components/ui";
import { api, fdate, money } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

const CATS = ["utilities", "repairs", "salary", "fuel", "services", "other"];
const METHODS = ["bank", "cash", "bkash", "nagad"];
type Sum = { year: number; income: number; expense: number; net: number; monthly: { month: string; income: number; expense: number }[]; categories: { category: string; actual: number; budget: number }[]; cash: Record<string, number>; cash_total: number; pending: number; to_pay: number };
type Exp = { id: number; category: string; title: string; amount: number; spent_on: string; status: string; needs_two: boolean; approvals: { user_id: number; name: string }[]; approvals_needed: number; requested_by: string; requested_by_id: number; vendor: string; vendor_bn: string; method: string; reason: string };
type Vendor = { id: number; name: string; name_bn: string };
type Asset = { id: number; name: string; name_bn: string; cost: number; bought_on: string; life_years: number; capitalised: boolean; status: string; depreciation: number; book_value: number; note: string };
type Jr = { id: number; date: string; memo: string; source: string; lines: { code: string; name: string; name_bn: string; debit: number; credit: number }[] };
type Trial = { rows: { code: string; name: string; name_bn: string; debit: number; credit: number }[]; debit: number; credit: number };
type Tab = "overview" | "expenses" | "budget" | "assets" | "ledger";
const stTone = (s: string) => (s === "paid" ? "ok" : s === "rejected" ? "bad" : s === "approved" ? "info" : "warn") as "ok" | "bad" | "info" | "warn";

export default function Finance() {
  const { t, pick } = useT(); const { prop, has, feature, user } = useAuth(); const toast = useToast();
  const viewer = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY", "TREASURER", "MEMBER", "AUDITOR");
  const approver = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "TREASURER"); const payer = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "TREASURER");
  const [tab, setTab] = useState<Tab>(viewer ? "overview" : "expenses"); const [sum, setSum] = useState<Sum | null>(null); const [exps, setExps] = useState<Exp[]>([]); const [vendors, setVendors] = useState<Vendor[]>([]);
  const [bud, setBud] = useState<Record<string, number>>({}); const [assets, setAssets] = useState<{ rows: Asset[]; cost: number; book_value: number } | null>(null);
  const [jr, setJr] = useState<{ total: number; rows: Jr[] }>({ total: 0, rows: [] }); const [trial, setTrial] = useState<Trial | null>(null); const [page, setPage] = useState(0);
  const [newExp, setNewExp] = useState(false); const [payFor, setPayFor] = useState<Exp | null>(null); const [rejFor, setRejFor] = useState<Exp | null>(null); const [newAsset, setNewAsset] = useState(false);

  const load = useCallback(async () => {
    setExps(await api("/finance/expenses")); setVendors(await api("/finance/vendors"));
    if (!viewer) return;
    setSum(await api("/finance/summary")); const b = await api<{ lines: Record<string, number> }>("/finance/budget"); setBud(b.lines);
    if (feature("assets")) setAssets(await api("/finance/assets"));
    setJr(await api(`/finance/ledger?limit=10&offset=${page * 10}`)); setTrial(await api("/finance/trial-balance"));
  }, [viewer, feature, page]);
  useEffect(() => { load(); }, [load, prop?.id]);
  const act = async (path: string, body?: unknown, ok?: string) => { try { await api(path, { method: "POST", body }); if (ok) toast.show(ok); load(); } catch (e: any) { toast.show(e.message); } };
  const myTurn = (e: Exp) => e.status === "pending" && approver && e.requested_by_id !== user?.id && !e.approvals.some((a) => a.user_id === user?.id);
  const waiting = exps.filter((e) => myTurn(e)); const topay = exps.filter((e) => e.status === "approved");
  const items = [{ id: "overview" as Tab, label: t("fin.tab.overview") }, { id: "expenses" as Tab, label: `${t("fin.tab.expenses")}${waiting.length ? ` · ${waiting.length}` : ""}` }, { id: "budget" as Tab, label: t("fin.tab.budget") }, ...(feature("assets") ? [{ id: "assets" as Tab, label: t("fin.tab.assets") }] : []), { id: "ledger" as Tab, label: t("fin.tab.ledger") }];
  const maxM = Math.max(1, ...(sum?.monthly ?? []).flatMap((m) => [m.income, m.expense]));
  const cname = (c: string) => t(`fin.cat.${c}`);

  return (<>
    <PageHead title={t("fin.title")} sub={t("fin.sub")} actions={<Btn onClick={() => setNewExp(true)}>{t("fin.new")}</Btn>} />
    {viewer && <div style={{ marginBottom: 16 }}><Tabs value={tab} onChange={setTab} items={items} /></div>}

    {tab === "overview" && sum && (<div className="stack">
      <div className="grid g4"><Stat label={`${t("fin.income")} · ${sum.year}`} value={money(sum.income)} /><Stat label={t("fin.expense")} value={money(sum.expense)} /><Stat label={t("fin.net")} value={money(sum.net)} />
        <Stat label={t("fin.cash")} value={money(sum.cash_total)} note={<span className="small">{Object.entries(sum.cash).map(([k, v]) => `${k === "1010" ? t("fin.method.cash") : k === "1020" ? t("fin.method.bank") : "bKash/Nagad"} ${money(v)}`).join(" · ")}</span>} /></div>
      <div className="grid g2">
        <Card><h3>{t("fin.month_trend")}</h3><div className="row" style={{ alignItems: "flex-end", gap: 14, height: 190, marginTop: 14, overflowX: "auto" }}>{sum.monthly.map((m) => (
          <div key={m.month} style={{ flex: 1, minWidth: 54, textAlign: "center" }}><div style={{ display: "flex", gap: 4, alignItems: "flex-end", height: 150, justifyContent: "center" }}>
            <div title={money(m.income)} style={{ width: 20, height: `${(m.income / maxM) * 100}%`, background: "var(--ok)", borderRadius: "6px 6px 0 0" }} /><div title={money(m.expense)} style={{ width: 20, height: `${(m.expense / maxM) * 100}%`, background: "var(--wine, #691542)", borderRadius: "6px 6px 0 0" }} /></div>
            <div className="small muted" style={{ marginTop: 6 }}>{m.month.slice(5)}</div></div>))}</div>
          <div className="row small" style={{ gap: 16, marginTop: 10 }}><span className="row" style={{ gap: 6 }}><i style={{ width: 12, height: 12, background: "var(--ok)", borderRadius: 3 }} />{t("fin.income")}</span><span className="row" style={{ gap: 6 }}><i style={{ width: 12, height: 12, background: "var(--wine, #691542)", borderRadius: 3 }} />{t("fin.expense")}</span></div></Card>
        <Card><h3>{t("fin.cat_budget")}</h3><div className="stack" style={{ gap: 12, marginTop: 12 }}>{sum.categories.map((c) => { const pct = c.budget ? (100 * c.actual) / c.budget : 0; return (
          <div key={c.category}><div className="row between small"><b>{cname(c.category)}</b><span className="muted">{money(c.actual)} / {money(c.budget)} {c.budget > 0 && (pct > 100 ? <Chip tone="bad">{t("fin.over")}</Chip> : <span>· {t("fin.used", { n: Math.round(pct) })}</span>)}</span></div><Bar pct={Math.min(100, pct)} /></div>); })}</div></Card></div>
      <Card><h3>{t("fin.to_decide")}</h3>{waiting.length + topay.length === 0 ? <Empty>{t("fin.none_wait")}</Empty> : [...waiting, ...topay].slice(0, 6).map((e) => (
        <div key={e.id} className="row between wrap" style={{ padding: "10px 0", borderTop: "1px solid var(--line)" }}><div><b>{e.title}</b><br /><span className="small muted">{money(e.amount)} · {cname(e.category)} · {e.requested_by}</span></div>
          <div className="row"><Chip tone={stTone(e.status)}>{t(`fin.st.${e.status}`)}</Chip>{myTurn(e) && <Btn size="sm" onClick={() => act(`/finance/expenses/${e.id}/approve`, undefined, t("fin.saved"))}>{t("fin.approve")}</Btn>}{e.status === "approved" && payer && <Btn size="sm" onClick={() => setPayFor(e)}>{t("fin.pay")}</Btn>}</div></div>))}</Card>
    </div>)}

    {tab === "expenses" && <DataTable rows={exps} pageSize={10} search={(r) => `${r.title} ${r.vendor} ${r.requested_by}`} cols={[
      { key: "d", head: t("fin.date"), render: (r) => <span className="nowrap">{fdate(r.spent_on)}</span> }, { key: "t", head: t("fin.title_f"), render: (r) => <><b>{r.title}</b><br /><span className="small muted">{cname(r.category)}{r.vendor ? ` · ${pick(r.vendor, r.vendor_bn || r.vendor)}` : ""}</span></> },
      { key: "a", head: t("common.amount"), num: true, render: (r) => <b>{money(r.amount)}</b> },
      { key: "s", head: t("common.status"), render: (r) => <><Chip tone={stTone(r.status)}>{t(`fin.st.${r.status}`)}</Chip>{r.status === "pending" && <div className="small muted">{t("fin.approvals", { a: r.approvals.length, n: r.approvals_needed })}</div>}{r.reason && <div className="small muted">{r.reason}</div>}</> },
      { key: "act", head: "", render: (r) => <div className="row">{myTurn(r) && <><Btn size="sm" onClick={() => act(`/finance/expenses/${r.id}/approve`, undefined, t("fin.saved"))}>{t("fin.approve")}</Btn><Btn size="sm" variant="outline" onClick={() => setRejFor(r)}>{t("fin.reject")}</Btn></>}{r.status === "approved" && payer && <Btn size="sm" onClick={() => setPayFor(r)}>{t("fin.pay")}</Btn>}</div> }]} />}

    {tab === "budget" && <BudgetTab bud={bud} edit={payer} onSave={async (lines) => { await api("/finance/budget", { method: "PUT", body: { year: sum?.year ?? new Date().getFullYear(), lines } }); toast.show(t("fin.saved")); load(); }} />}

    {tab === "assets" && assets && (<div className="stack">
      <div className="grid g3"><Stat label={t("fin.asset.total_cost")} value={money(assets.cost)} /><Stat label={t("fin.asset.total_book")} value={money(assets.book_value)} />{payer && <div style={{ display: "flex", alignItems: "center" }}><Btn onClick={() => setNewAsset(true)}>{t("fin.asset.add")}</Btn></div>}</div>
      <p className="hint">{t("fin.asset.rule")}</p>
      <DataTable rows={assets.rows} pageSize={10} cols={[{ key: "n", head: t("fin.asset.name"), render: (r) => <><b>{pick(r.name, r.name_bn || r.name)}</b>{!r.capitalised && <div className="small muted">{t("fin.asset.expensed")}</div>}</> }, { key: "b", head: t("fin.asset.bought"), render: (r) => <span className="nowrap">{fdate(r.bought_on)}</span> },
        { key: "c", head: t("fin.asset.cost"), num: true, render: (r) => money(r.cost) }, { key: "d", head: t("fin.asset.dep"), num: true, render: (r) => r.capitalised ? money(r.depreciation) : "–" }, { key: "v", head: t("fin.asset.book"), num: true, render: (r) => <b>{r.capitalised ? money(r.book_value) : "–"}</b> },
        { key: "s", head: "", render: (r) => <Chip tone={r.status === "in_use" ? "ok" : "mute"}>{t(`fin.asset.${r.status}`)}</Chip> }]} /></div>)}

    {tab === "ledger" && (<div className="stack"><p className="hint">{t("fin.ledger.note")}</p>
      {trial && <Card><div className="row between"><h3>{t("fin.ledger.trial")}</h3><Chip tone={trial.debit === trial.credit ? "ok" : "bad"}>{t("fin.ledger.balanced")}</Chip></div>
        <table className="t" style={{ marginTop: 10 }}><thead><tr><th>{t("fin.ledger.account")}</th><th className="num">{t("fin.ledger.debit")}</th><th className="num">{t("fin.ledger.credit")}</th></tr></thead><tbody>
          {trial.rows.filter((r) => r.debit || r.credit).map((r) => <tr key={r.code}><td><span className="muted">{r.code}</span> {pick(r.name, r.name_bn)}</td><td className="num">{r.debit ? money(r.debit) : ""}</td><td className="num">{r.credit ? money(r.credit) : ""}</td></tr>)}
          <tr><td><b>{t("common.total")}</b></td><td className="num"><b>{money(trial.debit)}</b></td><td className="num"><b>{money(trial.credit)}</b></td></tr></tbody></table></Card>}
      <Card><h3>{t("fin.ledger.journal")}</h3>{jr.rows.map((j) => (<div key={j.id} style={{ padding: "10px 0", borderTop: "1px solid var(--line)" }}><div className="row between"><b>{j.memo}</b><span className="small muted">{fdate(j.date)} · <Chip tone="mute">{t(`fin.src.${j.source}`)}</Chip></span></div>
        {j.lines.map((l, i) => <div key={i} className="row between small" style={{ paddingLeft: l.credit ? 24 : 0 }}><span>{l.code} {pick(l.name, l.name_bn)}</span><span>{l.debit ? money(l.debit) : money(l.credit)}</span></div>)}</div>))}
        <div className="row between" style={{ marginTop: 12 }}><span className="small muted">{t("common.total")}: {jr.total} · {t("common.page", { n: page + 1, m: Math.max(1, Math.ceil(jr.total / 10)) })}</span><div className="row"><Btn size="sm" variant="outline" disabled={page === 0} onClick={() => setPage(page - 1)}>{t("common.prev")}</Btn><Btn size="sm" variant="outline" disabled={(page + 1) * 10 >= jr.total} onClick={() => setPage(page + 1)}>{t("common.next")}</Btn></div></div></Card></div>)}

    {newExp && <ExpenseModal vendors={vendors} onClose={() => setNewExp(false)} onDone={() => { setNewExp(false); toast.show(t("fin.saved")); load(); }} />}
    {payFor && <PayModal e={payFor} onClose={() => setPayFor(null)} onDone={() => { setPayFor(null); toast.show(t("fin.saved")); load(); }} />}
    {rejFor && <RejectModal e={rejFor} onClose={() => setRejFor(null)} onDone={() => { setRejFor(null); load(); }} />}
    {newAsset && <AssetModal onClose={() => setNewAsset(false)} onDone={() => { setNewAsset(false); toast.show(t("fin.saved")); load(); }} />}
    {toast.node}
  </>);
}

function BudgetTab({ bud, edit, onSave }: { bud: Record<string, number>; edit: boolean; onSave: (l: Record<string, number>) => void }) {
  const { t } = useT(); const [v, setV] = useState<Record<string, string>>({});
  useEffect(() => { setV(Object.fromEntries(CATS.map((c) => [c, String((bud[c] ?? 0) / 100)]))); }, [bud]);
  const total = CATS.reduce((a, c) => a + Math.round(+(v[c] || 0) * 100), 0);
  return <Card><p className="hint">{t("fin.budget_note")}</p><div className="grid g3" style={{ marginTop: 10 }}>{CATS.map((c) => <Field key={c} label={t(`fin.cat.${c}`)}><input className="input" inputMode="decimal" disabled={!edit} value={v[c] ?? ""} onChange={(e) => setV({ ...v, [c]: e.target.value })} /></Field>)}</div>
    <div className="row between" style={{ marginTop: 6 }}><b>{t("fin.budget_total")}: {money(total)}</b>{edit && <Btn onClick={() => onSave(Object.fromEntries(CATS.map((c) => [c, Math.round(+(v[c] || 0) * 100)])))}>{t("fin.budget_save")}</Btn>}</div></Card>;
}

function ExpenseModal({ vendors, onClose, onDone }: { vendors: Vendor[]; onClose: () => void; onDone: () => void }) {
  const { t, pick } = useT(); const [f, setF] = useState({ category: "repairs", title: "", amount: "", spent_on: new Date().toISOString().slice(0, 10), vendor_id: "" }); const [err, setErr] = useState(""); const [list, setList] = useState(vendors); const [nv, setNv] = useState("");
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const go = async () => { try { await api("/finance/expenses", { body: { category: f.category, title: f.title, amount: Math.round(+f.amount * 100), spent_on: f.spent_on, vendor_id: f.vendor_id ? +f.vendor_id : null } }); onDone(); } catch (e: any) { setErr(e.message); } };
  const addV = async () => { const v = await api("/finance/vendors", { body: { name: nv } }); setList([...list, v]); setF({ ...f, vendor_id: String(v.id) }); setNv(""); };
  return <Modal title={t("fin.new")} onClose={onClose}>
    <Field label={t("fin.title_f")}><input className="input" value={f.title} onChange={set("title")} /></Field>
    <div className="grid g2"><Field label={t("fin.category")}><select className="input" value={f.category} onChange={set("category")}>{CATS.map((c) => <option key={c} value={c}>{t(`fin.cat.${c}`)}</option>)}</select></Field><Field label={t("common.amount") + " (BDT)"}><input className="input" inputMode="decimal" value={f.amount} onChange={set("amount")} /></Field></div>
    <div className="grid g2"><Field label={t("fin.date")}><input className="input" type="date" value={f.spent_on} onChange={set("spent_on")} /></Field><Field label={t("fin.vendor")}><select className="input" value={f.vendor_id} onChange={set("vendor_id")}><option value="">{t("fin.no_vendor")}</option>{list.map((v) => <option key={v.id} value={v.id}>{pick(v.name, v.name_bn || v.name)}</option>)}</select></Field></div>
    <div className="row" style={{ marginBottom: 10 }}><input className="input" placeholder={t("fin.vendor_name")} value={nv} onChange={(e) => setNv(e.target.value)} /><Btn variant="soft" onClick={addV} disabled={nv.trim().length < 2}>{t("fin.add_vendor")}</Btn></div>
    {+f.amount * 100 > 5_000_000 && <p className="hint">{t("fin.two_note")}</p>}{err && <p className="error" role="alert">{err}</p>}
    <div className="row"><Btn onClick={go} disabled={f.title.trim().length < 3 || !(+f.amount > 0)}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}
function PayModal({ e, onClose, onDone }: { e: Exp; onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [m, setM] = useState("bank"); const [err, setErr] = useState("");
  const go = async () => { try { await api(`/finance/expenses/${e.id}/pay`, { body: { method: m } }); onDone(); } catch (x: any) { setErr(x.message); } };
  return <Modal title={`${t("fin.pay")} · ${money(e.amount)}`} onClose={onClose}><p>{e.title}</p><Field label={t("fin.pay_with")}><select className="input" value={m} onChange={(x) => setM(x.target.value)}>{METHODS.map((k) => <option key={k} value={k}>{t(`fin.method.${k}`)}</option>)}</select></Field>{err && <p className="error">{err}</p>}<div className="row"><Btn onClick={go}>{t("fin.pay")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}
function RejectModal({ e, onClose, onDone }: { e: Exp; onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [r, setR] = useState("");
  return <Modal title={`${t("fin.reject")} · ${e.title}`} onClose={onClose}><Field label={t("fin.reason")}><input className="input" value={r} onChange={(x) => setR(x.target.value)} /></Field><div className="row"><Btn variant="danger" onClick={async () => { await api(`/finance/expenses/${e.id}/reject`, { body: { reason: r } }); onDone(); }}>{t("fin.reject")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}
function AssetModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [f, setF] = useState({ name: "", name_bn: "", cost: "", bought_on: new Date().toISOString().slice(0, 10), life_years: "10", method: "bank" }); const [err, setErr] = useState("");
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const go = async () => { try { await api("/finance/assets", { body: { name: f.name, name_bn: f.name_bn, cost: Math.round(+f.cost * 100), bought_on: f.bought_on, life_years: +f.life_years, method: f.method } }); onDone(); } catch (e: any) { setErr(e.message); } };
  return <Modal title={t("fin.asset.add")} onClose={onClose}><Field label={t("fin.asset.name")}><input className="input" value={f.name} onChange={set("name")} /></Field>
    <div className="grid g2"><Field label={t("fin.asset.cost")}><input className="input" inputMode="decimal" value={f.cost} onChange={set("cost")} /></Field><Field label={t("fin.asset.bought")}><input className="input" type="date" value={f.bought_on} onChange={set("bought_on")} /></Field>
      <Field label={t("fin.asset.life")}><input className="input" type="number" min={1} value={f.life_years} onChange={set("life_years")} /></Field><Field label={t("fin.asset.method")}><select className="input" value={f.method} onChange={set("method")}>{METHODS.map((k) => <option key={k} value={k}>{t(`fin.method.${k}`)}</option>)}</select></Field></div>
    <p className="hint">{t("fin.asset.rule")}</p>{err && <p className="error">{err}</p>}<div className="row"><Btn onClick={go} disabled={f.name.trim().length < 2 || !(+f.cost > 0)}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}
