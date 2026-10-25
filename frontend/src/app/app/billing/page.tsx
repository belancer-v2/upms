"use client";
import { useCallback, useEffect, useState } from "react";
import { BillChip, stColor, type Inv, type Pay } from "@/components/billbits";
import { PayForm } from "@/components/PayForm";
import { GatewayCard } from "@/components/GatewayCard";
import { ExportButton } from "@/components/ExportButton";
import { UnitMap, type Unit } from "@/components/UnitParts";
import { Bar, Btn, Card, Chip, DataTable, Empty, Field, Modal, PageHead, Stat, Tabs, useToast } from "@/components/ui";
import { api, fdate, money } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { periodLabel } from "@/lib/act";
import { useT } from "@/lib/i18n";

type Agg = { period: string; billed: number; collected: number; outstanding: number; pct: number; invoices: number; paid: number };
type Sum = { periods: string[]; current: Agg | null; trend: Agg[]; methods: Record<string, number>; pending: number };
type Dues = { total: number; buckets: Record<string, number>; rows: { unit_id: number; unit: string; name: string; name_bn: string; phone: string; outstanding: number; months: number; oldest_days: number; bucket: string }[] };
type Rule = { id: number; name: string; name_bn: string; kind: string; amount: number; active: boolean };
type Tab = "overview" | "invoices" | "payments" | "dues" | "rules";

export default function Billing() {
  const { t, pick } = useT(); const { prop, has, feature } = useAuth(); const toast = useToast();
  const money_roles = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "TREASURER");
  const [tab, setTab] = useState<Tab>("overview"); const [period, setPeriod] = useState("");
  const [sum, setSum] = useState<Sum | null>(null); const [units, setUnits] = useState<Unit[]>([]); const [map, setMap] = useState<Record<string, { status: string; balance: number }>>({});
  const [invs, setInvs] = useState<Inv[]>([]); const [pays, setPays] = useState<Pay[]>([]); const [dues, setDues] = useState<Dues | null>(null); const [rules, setRules] = useState<Rule[]>([]);
  const [gen, setGen] = useState(false); const [rec, setRec] = useState<Inv | null>(null); const [rule, setRule] = useState<Partial<Rule> | null>(null);

  const load = useCallback(async () => {
    const s = await api<Sum>(`/billing/summary${period ? `?period=${period}` : ""}`); setSum(s);
    const p = period || s.current?.period || "";
    if (p) setMap(await api(`/billing/map?period=${p}`));
    setInvs(await api(`/billing/invoices${p ? `?period=${p}` : ""}`));
    setPays(await api("/billing/payments")); setDues(await api("/billing/dues")); setRules(await api("/billing/rules"));
  }, [period]);
  useEffect(() => { api<Unit[]>("/units").then(setUnits); }, [prop?.id]);
  useEffect(() => { load(); }, [load, prop?.id]);
  if (!sum) return <p className="muted">{t("common.loading")}</p>;
  const cur = sum.current; const p = period || cur?.period || "";
  const decide = async (id: number, a: "verify" | "reject") => { await api(`/billing/payments/${id}/${a}`, { method: "POST" }); load(); };
  const remind = async () => { try { const r = await api<{ sent: number; failed: number }>("/billing/reminders/run", { method: "POST" }); toast.show(t("bill.remind_done", { s: r.sent, f: r.failed })); load(); } catch (e: any) { toast.show(e.status === 402 ? t("bill.remind_locked") : e.message); } };
  const pending = pays.filter((x) => x.status === "pending");
  const maxBilled = Math.max(1, ...sum.trend.map((x) => x.billed));

  return (<>
    <PageHead helpKey="run-invoices" title={t("bill.title")} sub={t("bill.sub")} actions={<>
      <select className="input" style={{ width: "auto" }} value={p} onChange={(e) => setPeriod(e.target.value)} aria-label={t("bill.period")}>{sum.periods.map((x) => <option key={x}>{x}</option>)}</select>
      {(tab === "invoices" || tab === "payments" || tab === "dues") && <ExportButton name={tab} />}
      {money_roles && <Btn onClick={() => setGen(true)}>{t("bill.generate")}</Btn>}</>} />
    <div style={{ marginBottom: 16 }}><Tabs value={tab} onChange={setTab} items={[{ id: "overview", label: t("bill.tab.overview") }, { id: "invoices", label: t("bill.tab.invoices") }, { id: "payments", label: `${t("bill.tab.payments")}${pending.length ? ` · ${pending.length}` : ""}` }, { id: "dues", label: t("bill.tab.dues") }, { id: "rules", label: t("bill.tab.rules") }]} /></div>

    {tab === "overview" && cur && (<div className="stack">
      <div className="grid g4">
        <Stat label={t("bill.billed")} value={money(cur.billed)} note={`${cur.invoices} ${t("bill.tab.invoices").toLowerCase()}`} />
        <Stat label={t("bill.collected")} value={money(cur.collected)} note={<Bar pct={cur.pct} spark />} />
        <Stat label={t("bill.outstanding")} value={money(cur.outstanding)} note={`${cur.invoices - cur.paid} / ${cur.invoices}`} />
        <Stat label={t("bill.rate")} value={`${cur.pct}%`} note={sum.pending ? <Chip tone="warn">{t("bill.pending_n", { n: sum.pending })}</Chip> : undefined} />
      </div>
      <div className="grid g2">
        <Card><h3>{t("bill.trend")}</h3>
          <div className="stack" style={{ gap: 10, marginTop: 12 }}>{sum.trend.map((x) => (
            <div key={x.period}><div className="row between small"><b>{x.period}</b><span className="muted">{money(x.collected)} / {money(x.billed)} · {x.pct}%</span></div>
              <div className="bar" style={{ width: `${(x.billed / maxBilled) * 100}%` }}><i style={{ width: `${x.pct}%` }} /></div></div>))}</div></Card>
        <Card><h3>{t("bill.methods")}</h3>
          <div className="stack" style={{ gap: 10, marginTop: 12 }}>{(["bkash", "nagad", "card", "bank", "cash"] as const).map((m) => { const v = sum.methods[m] ?? 0; const tot = Object.values(sum.methods).reduce((a, b) => a + b, 0) || 1; return (
            <div key={m}><div className="row between small"><b>{t(`bill.m.${m}`)}</b><span className="muted">{money(v)} · {Math.round((100 * v) / tot)}%</span></div><Bar pct={(100 * v) / tot} /></div>); })}</div></Card>
      </div>
      <Card><div className="row between wrap"><h3>{t("bill.map")} · {p}</h3>
        <div className="row wrap small">{(["paid", "partial", "open", "overdue"] as const).map((s) => <span key={s} className="row" style={{ gap: 6 }}><i style={{ width: 12, height: 12, borderRadius: 4, background: stColor(s).bg, border: `1px solid ${stColor(s).fg}` }} />{t(`bill.st.${s}`)}</span>)}</div></div>
        <div style={{ marginTop: 14, overflowX: "auto" }}><UnitMap units={units} onPick={(u) => { const i = invs.find((x) => x.unit_id === u.id); if (i) { setTab("invoices"); } }} color={(u) => stColor(map[u.id]?.status)} /></div></Card>
      {money_roles && <Card><div className="row between"><h3>{t("bill.pending")}</h3></div>
        {pending.length === 0 ? <Empty>{t("bill.empty_pending")}</Empty> : pending.slice(0, 5).map((x) => (
          <div key={x.id} className="row between wrap" style={{ padding: "10px 0", borderTop: "1px solid var(--line)" }}>
            <div><b>{x.unit}</b> · {money(x.amount)} · {t(`bill.m.${x.method}`)} {x.trx_id && <span className="muted small">· {x.trx_id}</span>}</div>
            <div className="row"><Btn size="sm" onClick={() => decide(x.id, "verify")}>{t("bill.verify")}</Btn><Btn size="sm" variant="outline" onClick={() => decide(x.id, "reject")}>{t("bill.reject")}</Btn></div></div>))}</Card>}
    </div>)}

    {tab === "invoices" && <DataTable rows={invs} pageSize={12} search={(r) => `${r.unit} ${r.number}`} cols={[
      { key: "unit", head: t("bill.flat"), render: (r) => <b>{r.unit}</b> }, { key: "period", head: t("bill.period"), render: (r) => periodLabel(t, r.period) }, { key: "due", head: t("bill.due"), render: (r) => <span className="nowrap">{fdate(r.due_date)}</span> },
      { key: "total", head: t("bill.total"), num: true, render: (r) => money(r.total) }, { key: "paid", head: t("bill.paid"), num: true, render: (r) => money(r.paid) },
      { key: "st", head: t("common.status"), render: (r) => <BillChip s={r.status} /> },
      { key: "act", head: "", render: (r) => money_roles && r.status !== "paid" && r.status !== "void" ? <Btn size="sm" variant="soft" onClick={() => setRec(r)}>{t("bill.record")}</Btn> : null }]} />}

    {tab === "payments" && <DataTable rows={pays} pageSize={12} search={(r) => `${r.unit} ${r.trx_id} ${r.receipt_no}`} cols={[
      { key: "unit", head: t("bill.flat"), render: (r) => <b>{r.unit}</b> }, { key: "period", head: t("bill.period"), render: (r) => periodLabel(t, r.period ?? "") }, { key: "amt", head: t("common.amount"), num: true, render: (r) => money(r.amount) },
      { key: "m", head: t("bill.method"), render: (r) => <>{t(`bill.m.${r.method}`)}{r.trx_id && <span className="muted small"> · {r.trx_id}</span>}</> },
      { key: "d", head: t("common.date"), render: (r) => <span className="nowrap">{fdate(r.paid_on)}</span> }, { key: "st", head: t("common.status"), render: (r) => <BillChip s={r.status} /> },
      { key: "act", head: "", render: (r) => r.status === "pending" && money_roles ? <div className="row"><Btn size="sm" onClick={() => decide(r.id, "verify")}>{t("bill.verify")}</Btn><Btn size="sm" variant="outline" onClick={() => decide(r.id, "reject")}>{t("bill.reject")}</Btn></div>
        : r.status === "verified" ? <a className="btn soft sm" href={`/app/receipt/${r.id}`}>{t("bill.receipt")}</a> : null }]} />}

    {tab === "dues" && dues && (<div className="stack">
      <div className="grid g4"><Stat label={t("bill.dues_total")} value={money(dues.total)} />{(["0-30", "31-60", "61+"] as const).map((b) => <Stat key={b} label={t(`bill.age.${b}`)} value={money(dues.buckets[b])} />)}</div>
      <div className="row between wrap"><h3>{t("bill.age")}</h3>{money_roles && <Btn variant={feature("reminders") ? "primary" : "outline"} onClick={remind}>{t("bill.remind")}</Btn>}</div>
      <DataTable rows={dues.rows.map((r) => ({ ...r, id: r.unit_id }))} pageSize={10} search={(r) => `${r.unit} ${r.name}`} cols={[
        { key: "unit", head: t("bill.flat"), render: (r) => <b>{r.unit}</b> }, { key: "n", head: t("common.name"), render: (r) => pick(r.name, r.name_bn) },
        { key: "m", head: "", render: (r) => t("bill.months", { n: r.months }) }, { key: "o", head: t("bill.age"), render: (r) => <Chip tone={r.bucket === "61+" ? "bad" : "warn"}>{t("bill.days", { n: r.oldest_days })}</Chip> },
        { key: "a", head: t("bill.outstanding"), num: true, render: (r) => <b>{money(r.outstanding)}</b> }]} /></div>)}

    {tab === "rules" && (<div className="stack">
      <div className="row between"><p className="hint" style={{ margin: 0 }}>{t("bill.rule.note")}</p>{money_roles && <Btn onClick={() => setRule({ kind: "flat", active: true })}>{t("bill.rule.add")}</Btn>}</div>
      <DataTable rows={rules} pageSize={10} cols={[{ key: "n", head: t("common.name"), render: (r) => <b>{pick(r.name, r.name_bn || r.name)}</b> }, { key: "k", head: t("bill.rule.kind"), render: (r) => t(r.kind === "flat" ? "bill.rule.flat" : "bill.rule.sqft") },
        { key: "a", head: t("common.amount"), num: true, render: (r) => money(r.amount) + (r.kind === "per_sqft" ? " / sq ft" : "") }, { key: "s", head: "", render: (r) => <Chip tone={r.active ? "ok" : "mute"}>{r.active ? t("bill.rule.active") : "–"}</Chip> },
        { key: "e", head: "", render: (r) => money_roles ? <Btn size="sm" variant="ghost" onClick={() => setRule(r)}>{t("common.edit")}</Btn> : null }]} />
      {money_roles && feature("gateway") && <GatewayCard onSaved={(m) => toast.show(m)} />}</div>)}

    {gen && <GenModal onClose={() => setGen(false)} onDone={(n) => { setGen(false); toast.show(n ? t("bill.gen_done", { n }) : t("bill.gen_none")); load(); }} />}
    {rec && <RecordModal inv={rec} onClose={() => setRec(null)} onDone={() => { setRec(null); toast.show(t("bill.recorded")); load(); }} />}
    {rule && <RuleModal rule={rule} onClose={() => setRule(null)} onDone={() => { setRule(null); toast.show(t("bill.rule.saved")); load(); }} />}
    {toast.node}
  </>);
}

function GenModal({ onClose, onDone }: { onClose: () => void; onDone: (n: number) => void }) {
  const { t } = useT(); const d = new Date(); const [period, setPeriod] = useState(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`); const [due, setDue] = useState(10); const [err, setErr] = useState("");
  const go = async () => { try { const r = await api<{ created: number }>("/billing/run", { body: { period, due_day: due } }); onDone(r.created); } catch (e: any) { setErr(e.message); } };
  return <Modal title={t("bill.generate")} onClose={onClose}>
    <div className="grid g2"><Field label={t("bill.gen_for")}><input className="input" value={period} onChange={(e) => setPeriod(e.target.value)} /></Field><Field label={t("bill.gen_due")}><input className="input" type="number" min={1} max={28} value={due} onChange={(e) => setDue(+e.target.value)} /></Field></div>
    {err && <p className="error" role="alert">{err}</p>}<div className="row"><Btn onClick={go}>{t("bill.generate")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}

function RecordModal({ inv, onClose, onDone }: { inv: Inv; onClose: () => void; onDone: () => void }) { return <PayForm inv={inv} staff onClose={onClose} onDone={onDone} />; }

function RuleModal({ rule, onClose, onDone }: { rule: Partial<Rule>; onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [f, setF] = useState({ name: rule.name ?? "", name_bn: rule.name_bn ?? "", kind: rule.kind ?? "flat", amount: String((rule.amount ?? 0) / 100), active: rule.active ?? true }); const [err, setErr] = useState("");
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value });
  const go = async () => { try { const body = { ...f, amount: Math.round(+f.amount * 100) }; await api(rule.id ? `/billing/rules/${rule.id}` : "/billing/rules", { method: rule.id ? "PUT" : "POST", body }); onDone(); } catch (e: any) { setErr(e.message); } };
  return <Modal title={rule.id ? t("common.edit") : t("bill.rule.add")} onClose={onClose}>
    <Field label={t("bill.rule.name")}><input className="input" value={f.name} onChange={set("name")} /></Field><Field label={t("bill.rule.name_bn")}><input className="input" value={f.name_bn} onChange={set("name_bn")} /></Field>
    <div className="grid g2"><Field label={t("bill.rule.kind")}><select className="input" value={f.kind} onChange={set("kind")}><option value="flat">{t("bill.rule.flat")}</option><option value="per_sqft">{t("bill.rule.sqft")}</option></select></Field>
      <Field label={t("bill.rule.amount")}><input className="input" inputMode="decimal" value={f.amount} onChange={set("amount")} /></Field></div>
    <label className="row" style={{ marginBottom: 12 }}><input type="checkbox" checked={f.active} onChange={set("active")} /> {t("bill.rule.active")}</label>
    {err && <p className="error" role="alert">{err}</p>}<div className="row"><Btn onClick={go} disabled={f.name.trim().length < 2}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}
