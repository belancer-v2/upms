"use client";
import { useCallback, useEffect, useState } from "react";
import { Pager } from "@/components/pager";
import { authHeaders } from "@/components/Avatar";
import { Btn, Card, Chip, Empty, Field, Modal, PageHead, Stat, Tabs, useToast } from "@/components/ui";
import { api, fdate, money } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

const KINDS = ["lift", "generator", "cctv", "fire", "pest", "other"];
type Row = { id: number; kind: string; title: string; vendor_id: number | null; vendor: string; vendor_bn: string; start_date: string; end_date: string; annual_cost: number; interval_days: number; status: string; note: string;
  visits: number; last_visit: string | null; days_left: number; expired: boolean; renewal_due: boolean; next_due: string | null; visit_overdue: boolean; visit_due_soon: boolean };
type Visit = { id: number; visited_on: string; technician: string; notes: string; cost: number; expense_id: number | null };
type Doc = { id: number; visit_id: number | null; kind: string; filename: string; size: number };
type Detail = Row & { visit_list: Visit[]; docs: Doc[]; can_write: boolean; can_log: boolean; can_expense: boolean };
type Sum = { active: number; annual_cost: number; renewal: number; expired: number; visit_overdue: number; visit_soon: number };
const paisa = (v: string) => Math.max(0, Math.round(parseFloat(v || "0") * 100));
const today = () => new Date().toISOString().slice(0, 10);

function ContractChips({ r }: { r: Row }) {
  const { t } = useT();
  return <span className="row wrap" style={{ gap: 6 }}>
    {r.status === "ended" ? <Chip tone="mute">{t("ct.st.ended")}</Chip> : r.expired ? <Chip tone="bad">{t("ct.expired")}</Chip> : r.renewal_due ? <Chip tone="warn">{t("ct.renew_in", { n: r.days_left })}</Chip> : <Chip tone="ok">{t("ct.st.active")}</Chip>}
    {r.visit_overdue && <Chip tone="bad">{t("ct.visit_overdue")}</Chip>}{!r.visit_overdue && r.visit_due_soon && <Chip tone="info">{t("ct.visit_soon")}</Chip>}</span>;
}

export default function Contracts() {
  const { t, pick } = useT(); const { prop, has } = useAuth(); const toast = useToast(); const write = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "SECRETARY");
  const [s, setS] = useState<Sum | null>(null); const [rows, setRows] = useState<Row[] | null>(null); const [total, setTotal] = useState(0); const [page, setPage] = useState(1); const size = 10;
  const [q, setQ] = useState(""); const [kind, setKind] = useState(""); const [status, setStatus] = useState(""); const [open, setOpen] = useState<number | null>(null); const [form, setForm] = useState<Row | "new" | null>(null); const [err, setErr] = useState("");
  const load = useCallback(() => {
    api<Sum>("/contracts/summary").then(setS).catch((e) => setErr(e.message));
    api<{ items: Row[]; total: number }>(`/contracts?page=${page}&size=${size}&q=${encodeURIComponent(q)}&kind=${kind}&status=${status}`).then((d) => { setRows(d.items); setTotal(d.total); }).catch((e) => setErr(e.message));
  }, [page, q, kind, status]);
  useEffect(() => { load(); }, [load, prop?.id]);
  if (err) return <p className="error" role="alert">{err}</p>;
  return (<>
    <PageHead title={t("ct.title")} sub={t("ct.sub")} actions={write && <Btn onClick={() => setForm("new")}>{t("ct.add")}</Btn>} />
    {s && <div className="grid g4" style={{ marginBottom: 16 }}>
      <Stat label={t("ct.stat.active")} value={s.active} />
      <Stat label={t("ct.stat.cost")} value={money(s.annual_cost)} />
      <Stat label={t("ct.stat.renewal")} value={s.renewal + s.expired} note={s.expired ? t("ct.stat.expired", { n: s.expired }) : undefined} />
      <Stat label={t("ct.stat.overdue")} value={s.visit_overdue} note={s.visit_soon ? t("ct.stat.soon", { n: s.visit_soon }) : undefined} /></div>}
    <div className="toolbar row wrap" style={{ marginBottom: 12 }}>
      <input className="input" style={{ maxWidth: 260 }} placeholder={t("ct.search")} aria-label={t("common.search")} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
      <select className="input" style={{ width: "auto" }} aria-label={t("ct.f.kind")} value={kind} onChange={(e) => { setKind(e.target.value); setPage(1); }}><option value="">{t("ct.all_kinds")}</option>{KINDS.map((k) => <option key={k} value={k}>{t(`ct.kind.${k}`)}</option>)}</select>
      <select className="input" style={{ width: "auto" }} aria-label={t("common.status")} value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}><option value="">{t("ct.all_status")}</option><option value="active">{t("ct.st.active")}</option><option value="ended">{t("ct.st.ended")}</option></select></div>
    {!rows ? <p className="muted">{t("common.loading")}</p> : rows.length === 0 ? <Card><Empty>{t("ct.none")}</Empty></Card> :
      <div className="stack">{rows.map((r) => (
        <Card key={r.id} style={{ padding: 16 }}>
          <div className="row between wrap" style={{ gap: 12 }}>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div className="row wrap" style={{ gap: 8, marginBottom: 6 }}><Chip tone="info">{t(`ct.kind.${r.kind}`)}</Chip><ContractChips r={r} /></div>
              <h3 style={{ margin: 0 }}>{r.title}</h3>
              <span className="small muted">{pick(r.vendor, r.vendor_bn || r.vendor)} · {t("ct.ends", { d: fdate(r.end_date) })} · {money(r.annual_cost)} {t("ct.per_year")}</span><br />
              <span className="small muted">{r.last_visit ? t("ct.last", { d: fdate(r.last_visit) }) : t("ct.no_visit")}{r.next_due ? ` · ${t(r.visit_overdue ? "ct.next_overdue" : "ct.next", { d: fdate(r.next_due) })}` : ""}</span>
            </div>
            <Btn variant="soft" onClick={() => setOpen(r.id)}>{t("common.view")}</Btn></div></Card>))}</div>}
    <Pager page={page} size={size} total={total} onPage={setPage} />
    {open !== null && <DetailModal id={open} onClose={() => { setOpen(null); load(); }} onEdit={(r) => { setOpen(null); setForm(r); }} toast={toast.show} />}
    {form && <ContractForm row={form === "new" ? null : form} onClose={() => setForm(null)} onDone={() => { setForm(null); toast.show(t("ct.saved")); load(); }} />}
    {toast.node}
  </>);
}

function DetailModal({ id, onClose, onEdit, toast }: { id: number; onClose: () => void; onEdit: (r: Row) => void; toast: (m: string) => void }) {
  const { t, pick } = useT(); const [d, setD] = useState<Detail | null>(null); const [tab, setTab] = useState<"visits" | "docs">("visits"); const [add, setAdd] = useState(false); const [err, setErr] = useState("");
  const load = useCallback(() => api<Detail>(`/contracts/${id}`).then(setD).catch((e) => setErr(e.message)), [id]);
  useEffect(() => { load(); }, [load]);
  if (err) return <Modal title={t("ct.title")} onClose={onClose}><p className="error">{err}</p></Modal>;
  if (!d) return <Modal title={t("ct.title")} onClose={onClose}><p className="muted">{t("common.loading")}</p></Modal>;
  const mkExpense = async (v: Visit) => {
    let amount: number | undefined;
    if (!v.cost) { const a = window.prompt(t("ct.expense_amount")); if (!a) return; amount = paisa(a); }
    try { await api(`/contracts/${d.id}/visits/${v.id}/expense`, { body: amount ? { amount } : {} }); toast(t("ct.expense_done")); load(); } catch (e: any) { toast(e.message); }
  };
  const openDoc = async (doc: Doc) => { const r = await fetch(`/api/contracts/${d.id}/docs/${doc.id}`, { headers: authHeaders() }); if (r.ok) window.open(URL.createObjectURL(await r.blob()), "_blank"); };
  const rmDoc = async (doc: Doc) => { if (!confirm(t("ct.doc_confirm"))) return; try { await api(`/contracts/${d.id}/docs/${doc.id}`, { method: "DELETE" }); load(); } catch (e: any) { toast(e.message); } };
  const upload = async (file: File | undefined, kind: string, visit?: number) => {
    if (!file) return; const fd = new FormData(); fd.append("file", file); fd.append("kind", kind); if (visit) fd.append("visit_id", String(visit));
    const r = await fetch(`/api/contracts/${d.id}/docs`, { method: "POST", headers: authHeaders(), body: fd });
    if (!r.ok) { const j = await r.json().catch(() => ({})); toast(typeof j.detail === "string" ? j.detail : r.statusText); return; }
    toast(t("ct.doc_saved")); load();
  };
  return (<Modal title={d.title} onClose={onClose}>
    <div className="row wrap" style={{ gap: 8, marginBottom: 10 }}><Chip tone="info">{t(`ct.kind.${d.kind}`)}</Chip><ContractChips r={d} /></div>
    <p className="small muted" style={{ margin: "0 0 12px" }}>{pick(d.vendor, d.vendor_bn || d.vendor)} · {fdate(d.start_date)} → {fdate(d.end_date)} · {money(d.annual_cost)} {t("ct.per_year")} · {t("ct.every", { n: d.interval_days })}</p>
    {d.note && <p className="small">{d.note}</p>}
    <div className="row wrap" style={{ marginBottom: 12 }}>
      {d.can_write && <Btn size="sm" variant="soft" onClick={() => onEdit(d)}>{t("common.edit")}</Btn>}
      {d.can_write && d.status === "active" && <Btn size="sm" variant="ghost" onClick={async () => { if (confirm(t("ct.end_confirm"))) { await api(`/contracts/${d.id}`, { method: "PUT", body: { status: "ended" } }); load(); } }}>{t("ct.end")}</Btn>}
      {d.can_write && d.status === "ended" && <Btn size="sm" variant="ghost" onClick={async () => { await api(`/contracts/${d.id}`, { method: "PUT", body: { status: "active" } }); load(); }}>{t("ct.reopen")}</Btn>}</div>
    <Tabs value={tab} onChange={setTab} items={[{ id: "visits", label: `${t("ct.visits")} · ${d.visit_list.length}` }, { id: "docs", label: `${t("ct.docs")} · ${d.docs.length}` }]} />
    {tab === "visits" && <div style={{ marginTop: 12 }}>
      {d.can_log && <Btn size="sm" onClick={() => setAdd(true)}>{t("ct.visit_add")}</Btn>}
      {d.visit_list.length === 0 ? <p className="muted small">{t("ct.visit_none")}</p> : d.visit_list.map((v) => (
        <div key={v.id} style={{ padding: "10px 0", borderTop: "1px solid var(--line)" }}>
          <div className="row between wrap" style={{ gap: 8 }}><b>{fdate(v.visited_on)}</b><span className="small muted">{v.technician || "–"}{v.cost ? ` · ${money(v.cost)}` : ""}</span></div>
          {v.notes && <p className="small" style={{ margin: "4px 0" }}>{v.notes}</p>}
          <div className="row wrap" style={{ gap: 6 }}>
            {v.expense_id ? <Chip tone="ok">{t("ct.expense_linked")}</Chip> : d.can_expense && <Btn size="sm" variant="soft" onClick={() => mkExpense(v)}>{t("ct.expense")}</Btn>}
            {d.can_log && <label className="btn btn-ghost btn-sm" style={{ cursor: "pointer" }}>{t("ct.doc_report")}<input type="file" hidden accept="application/pdf,image/jpeg,image/png" onChange={(e) => { upload(e.target.files?.[0], "report", v.id); e.target.value = ""; }} /></label>}
            {d.docs.filter((x) => x.visit_id === v.id).map((x) => <button key={x.id} className="btn btn-ghost btn-sm" onClick={() => openDoc(x)}>{x.filename}</button>)}</div></div>))}</div>}
    {tab === "docs" && <div style={{ marginTop: 12 }}>
      {d.can_log && <label className="btn btn-primary btn-sm" style={{ cursor: "pointer" }}>{t("ct.doc_add")}<input type="file" hidden accept="application/pdf,image/jpeg,image/png" onChange={(e) => { upload(e.target.files?.[0], "contract"); e.target.value = ""; }} /></label>}
      <p className="hint">{t("ct.doc_hint")}</p>
      {d.docs.length === 0 ? <p className="muted small">{t("ct.doc_none")}</p> : d.docs.map((x) => (
        <div key={x.id} className="row between wrap" style={{ padding: "8px 0", borderTop: "1px solid var(--line)" }}>
          <span><Chip tone="mute">{t(`ct.doc_kind.${x.kind}`)}</Chip> <button className="btn btn-ghost btn-sm" onClick={() => openDoc(x)}>{x.filename}</button></span>
          {d.can_write && <Btn size="sm" variant="ghost" onClick={() => rmDoc(x)}>{t("ct.doc_remove")}</Btn>}</div>))}</div>}
    {add && <VisitForm id={d.id} onClose={() => setAdd(false)} onDone={() => { setAdd(false); toast(t("ct.visit_saved")); load(); }} />}
  </Modal>);
}

function VisitForm({ id, onClose, onDone }: { id: number; onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [f, setF] = useState({ visited_on: today(), technician: "", notes: "", cost: "" }); const [err, setErr] = useState("");
  const go = async () => { try { await api(`/contracts/${id}/visits`, { body: { visited_on: f.visited_on, technician: f.technician, notes: f.notes, cost: paisa(f.cost) } }); onDone(); } catch (e: any) { setErr(e.message); } };
  return (<Modal title={t("ct.visit_add")} onClose={onClose}>
    <div className="grid g2"><Field label={t("ct.visit_date")}><input className="input" type="date" max={today()} value={f.visited_on} onChange={(e) => setF({ ...f, visited_on: e.target.value })} /></Field>
      <Field label={t("ct.technician")}><input className="input" value={f.technician} onChange={(e) => setF({ ...f, technician: e.target.value })} /></Field></div>
    <Field label={t("ct.notes")}><textarea className="input" rows={3} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
    <Field label={t("ct.cost_visit")} hint={t("ct.cost_hint")}><input className="input" inputMode="decimal" value={f.cost} onChange={(e) => setF({ ...f, cost: e.target.value })} /></Field>
    {err && <p className="error" role="alert">{err}</p>}<div className="row"><Btn onClick={go} disabled={!f.visited_on}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>);
}

function ContractForm({ row, onClose, onDone }: { row: Row | null; onClose: () => void; onDone: () => void }) {
  const { t, pick } = useT(); const { has, feature } = useAuth();
  const [f, setF] = useState({ kind: row?.kind ?? "lift", title: row?.title ?? "", vendor: row ? (row.vendor_id ? String(row.vendor_id) : "other") : "other", vendor_name: row && !row.vendor_id ? row.vendor : "", start_date: row?.start_date ?? today(),
    end_date: row?.end_date ?? "", cost: row ? String(row.annual_cost / 100) : "", every: String(row?.interval_days ?? 90), note: row?.note ?? "" });
  const [vendors, setVendors] = useState<{ id: number; name: string; name_bn: string }[]>([]); const [err, setErr] = useState("");
  useEffect(() => { if (feature("expenses") && has("PROPERTY_ADMIN", "AGENCY_MANAGER", "SECRETARY")) api<any[]>("/finance/vendors").then(setVendors).catch(() => {}); }, [feature, has]);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  const go = async () => {
    const body: any = { title: f.title, start_date: f.start_date, end_date: f.end_date, annual_cost: paisa(f.cost), interval_days: parseInt(f.every || "90", 10), note: f.note };
    if (f.vendor === "other") { body.vendor_name = f.vendor_name; body.vendor_id = null; } else body.vendor_id = +f.vendor;
    try { if (row) await api(`/contracts/${row.id}`, { method: "PUT", body }); else await api("/contracts", { body: { ...body, kind: f.kind } }); onDone(); } catch (e: any) { setErr(e.message); }
  };
  return (<Modal title={t(row ? "ct.edit" : "ct.add")} onClose={onClose}>
    {!row && <Field label={t("ct.f.kind")}><select className="input" value={f.kind} onChange={set("kind")}>{KINDS.map((k) => <option key={k} value={k}>{t(`ct.kind.${k}`)}</option>)}</select></Field>}
    <Field label={t("ct.f.title")}><input className="input" value={f.title} onChange={set("title")} /></Field>
    <Field label={t("ct.f.vendor")}><select className="input" value={f.vendor} onChange={set("vendor")}><option value="other">{t("ct.f.vendor_other")}</option>{vendors.map((v) => <option key={v.id} value={v.id}>{pick(v.name, v.name_bn || v.name)}</option>)}</select></Field>
    {f.vendor === "other" && <Field label={t("ct.f.vendor_name")}><input className="input" value={f.vendor_name} onChange={set("vendor_name")} /></Field>}
    <div className="grid g2"><Field label={t("ct.f.start")}><input className="input" type="date" value={f.start_date} onChange={set("start_date")} /></Field><Field label={t("ct.f.end")}><input className="input" type="date" value={f.end_date} onChange={set("end_date")} /></Field>
      <Field label={t("ct.f.cost")}><input className="input" inputMode="decimal" value={f.cost} onChange={set("cost")} /></Field><Field label={t("ct.f.every")} hint={t("ct.f.every_hint")}><input className="input" inputMode="numeric" value={f.every} onChange={set("every")} /></Field></div>
    <Field label={t("ct.f.note")}><textarea className="input" rows={2} value={f.note} onChange={set("note")} /></Field>
    {err && <p className="error" role="alert">{err}</p>}<div className="row"><Btn onClick={go} disabled={f.title.trim().length < 3 || !f.end_date}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>);
}
