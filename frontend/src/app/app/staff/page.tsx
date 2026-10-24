"use client";
import { useCallback, useEffect, useState } from "react";
import { Btn, Card, Chip, DataTable, Field, Modal, PageHead, Stat, Tabs, useToast } from "@/components/ui";
import { Avatar } from "@/components/Avatar";
import { ProfileModal } from "@/components/ProfilePanel";
import { DutyStrip } from "@/components/DutyStrip";
import { api, fdate, ftime, money } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

const ROLES = ["caretaker", "guard", "cleaner", "driver", "other"];
type S = { id: number; name: string; name_bn: string; role: string; phone: string; joined: string; salary: number; status: string; nid: string; has_nid: boolean; agency?: { agency_id: number; name: string; name_bn: string; emp_no: string; substitute: boolean } | null };
type Sh = { id: number; period: string; status: string; total: number; people: number; created_by: string; created_by_id: number; approved_by: string; paid_on: string | null; method: string; lines?: Ln[] };
type Ln = { id: number; staff_id: number; name: string; name_bn: string; role: string; base: number; bonus: number; deduction: number; net: number; bonus_kind: string; note: string };
const tone = (s: string) => (s === "paid" ? "ok" : s === "approved" ? "info" : "warn") as "ok" | "info" | "warn";

export default function Staff() {
  const { t, pick } = useT(); const { prop, has, user } = useAuth(); const toast = useToast();
  const edit = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "SECRETARY"); const prepare = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "TREASURER"); const approve = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT"); const reveal = approve;
  const [tab, setTab] = useState<"people" | "payroll">("people"); const [rows, setRows] = useState<S[]>([]); const [sheets, setSheets] = useState<Sh[]>([]); const [open, setOpen] = useState<Sh | null>(null);
  const [form, setForm] = useState<Partial<S> | null>(null); const [nid, setNid] = useState<S | null>(null); const [prof, setProf] = useState<S | null>(null); const [newSheet, setNewSheet] = useState(false);
  const load = useCallback(async () => { setRows(await api("/staff?employer=all")); setSheets(await api("/staff/payroll/sheets")); }, []);
  useEffect(() => { load(); }, [load, prop?.id]);
  const openSheet = async (id: number) => setOpen(await api(`/staff/payroll/sheets/${id}`));
  const active = rows.filter((r) => r.status === "active"); const [emp, setEmp] = useState("all");
  const agencies = Array.from(new Map(rows.filter((r) => r.agency).map((r) => [r.agency!.agency_id, r.agency!])).values());
  const shown = rows.filter((r) => emp === "all" || (emp === "direct" ? !r.agency : r.agency?.agency_id === +emp));
  return (<>
    <PageHead title={t("staff.title")} sub={t("staff.sub")} actions={tab === "people" ? (edit && <Btn onClick={() => setForm({ role: "guard" })}>{t("staff.add")}</Btn>) : (prepare && <Btn onClick={() => setNewSheet(true)}>{t("pay.sheet_new")}</Btn>)} />
    <div style={{ marginBottom: 16 }}><Tabs value={tab} onChange={(v) => { setTab(v); setOpen(null); }} items={[{ id: "people", label: `${t("staff.tab.people")} · ${active.length}` }, { id: "payroll", label: t("staff.tab.payroll") }]} /></div>

    {tab === "people" && (<div className="stack"><div className="grid g3"><Stat label={t("staff.tab.people")} value={active.length} /><Stat label={t("staff.total_pay")} value={money(active.reduce((a, r) => a + r.salary, 0))} /></div>
      <DutyStrip compact />
      <div className="row"><select className="input" style={{ width: "auto" }} value={emp} onChange={(e) => setEmp(e.target.value)} aria-label={t("ag.f.agency")}><option value="all">{t("ag.f.all")}</option><option value="direct">{t("ag.f.direct")}</option>{agencies.map((a) => <option key={a.agency_id} value={a.agency_id}>{pick(a.name, a.name_bn || a.name)}</option>)}</select></div>
      <DataTable rows={shown} pageSize={10} search={(r) => `${r.name} ${r.phone}`} cols={[
        { key: "n", head: t("common.name"), render: (r) => <span className="row" style={{ gap: 10 }}><Avatar kind="staff" id={r.id} name={pick(r.name, r.name_bn || r.name)} size={36} /><span><b>{pick(r.name, r.name_bn || r.name)}</b><br /><span className="small muted">{t(`staff.role.${r.role}`)}</span>{r.agency && <> <Chip tone="info">{t("ag.agency_chip")}: {pick(r.agency.name, r.agency.name_bn || r.agency.name)}</Chip>{r.agency.substitute && <> <Chip tone="warn">{t("ag.chip_sub")}</Chip></>}</>}</span></span> }, { key: "p", head: t("staff.phone"), render: (r) => r.phone || "–" },
        { key: "j", head: t("staff.joined"), render: (r) => <span className="nowrap">{fdate(r.joined)}</span> }, { key: "s", head: t("staff.salary"), num: true, render: (r) => money(r.salary) },
        { key: "i", head: t("staff.nid"), render: (r) => <span className="row" style={{ gap: 8 }}><code>{r.has_nid ? r.nid : t("staff.no_nid")}</code>{reveal && r.has_nid && <Btn size="sm" variant="ghost" onClick={() => setNid(r)}>{t("staff.reveal")}</Btn>}</span> },
        { key: "st", head: "", render: (r) => <Chip tone={r.status === "active" ? "ok" : "mute"}>{t(r.status === "active" ? "staff.active" : "staff.left")}</Chip> },
        { key: "e", head: "", render: (r) => <span className="row" style={{ gap: 6 }}>{edit && r.status === "active" && <Btn size="sm" variant="ghost" onClick={() => setForm(r)}>{t("common.edit")}</Btn>}<Btn size="sm" variant="ghost" onClick={() => setProf(r)}>{t("prof.open")}</Btn></span> }]} /></div>)}

    {tab === "payroll" && !open && <DataTable rows={sheets} pageSize={12} cols={[{ key: "p", head: t("pay.sheet"), render: (r) => <b>{r.period}</b> }, { key: "n", head: "", render: (r) => t("pay.people", { n: r.people }) }, { key: "t", head: t("pay.total"), num: true, render: (r) => <b>{money(r.total)}</b> },
      { key: "s", head: t("common.status"), render: (r) => <Chip tone={tone(r.status)}>{t(`pay.st.${r.status}`)}</Chip> }, { key: "o", head: "", render: (r) => <Btn size="sm" variant="soft" onClick={() => openSheet(r.id)}>{t("common.view")}</Btn> }]} />}
    {tab === "payroll" && open && <SheetView sh={open} prepare={prepare} approve={approve && open.created_by_id !== user?.id} onBack={() => { setOpen(null); load(); }} onChange={async () => { await openSheet(open.id); load(); }} toast={toast.show} />}

    {form && <StaffForm s={form} onClose={() => setForm(null)} onDone={() => { setForm(null); toast.show(t("staff.saved")); load(); }} onLeave={async (id) => { await api(`/staff/${id}/leave`, { method: "POST" }); setForm(null); load(); }} />}
    {prof && <ProfileModal kind="staff" id={prof.id} name={pick(prof.name, prof.name_bn || prof.name)} onClose={() => setProf(null)} />}
    {nid && <NidModal s={nid} onClose={() => setNid(null)} />}
    {newSheet && <NewSheetModal onClose={() => setNewSheet(false)} onDone={(id) => { setNewSheet(false); load(); openSheet(id); }} />}
    {toast.node}
  </>);
}

function SheetView({ sh, prepare, approve, onBack, onChange, toast }: { sh: Sh; prepare: boolean; approve: boolean; onBack: () => void; onChange: () => void; toast: (m: string) => void }) {
  const { t, pick } = useT(); const [pct, setPct] = useState("50"); const [method, setMethod] = useState("bank"); const draft = sh.status === "draft"; const [ed, setEd] = useState<Ln | null>(null);
  const run = async (p: string, body?: unknown, msg?: (r: any) => string) => { try { const r = await api(p, { body, method: "POST" }); if (msg) toast(msg(r)); onChange(); } catch (e: any) { toast(e.message); } };
  return (<div className="stack">
    <div className="row between wrap"><div className="row"><Btn variant="ghost" onClick={onBack}>← {t("pay.back")}</Btn><h2 style={{ margin: 0 }}>{sh.period}</h2><Chip tone={tone(sh.status)}>{t(`pay.st.${sh.status}`)}</Chip></div>
      <div className="small muted">{t("pay.prepared")}: {sh.created_by}{sh.approved_by && ` · ${t("pay.approved_by")}: ${sh.approved_by}`}{sh.paid_on && ` · ${t("pay.paid_on")}: ${fdate(sh.paid_on)}`}</div></div>
    <DataTable rows={sh.lines ?? []} pageSize={20} cols={[{ key: "n", head: t("common.name"), render: (r) => <><b>{pick(r.name, r.name_bn || r.name)}</b><br /><span className="small muted">{t(`staff.role.${r.role}`)}</span></> }, { key: "b", head: t("pay.base"), num: true, render: (r) => money(r.base) },
      { key: "o", head: t("pay.bonus"), num: true, render: (r) => <>{r.bonus ? money(r.bonus) : "–"}{r.bonus_kind && <Chip tone="info">{t(r.bonus_kind === "eid" ? "pay.eid_tag" : "pay.other_tag")}</Chip>}</> }, { key: "d", head: t("pay.deduction"), num: true, render: (r) => (r.deduction ? money(r.deduction) : "–") },
      { key: "net", head: t("pay.net"), num: true, render: (r) => <b>{money(r.net)}</b> },
      { key: "a", head: "", render: (r) => <div className="row">{draft && prepare && <Btn size="sm" variant="ghost" onClick={() => setEd(r)}>{t("common.edit")}</Btn>}<a className="btn soft sm" href={`/app/payslip/${r.id}`}>{t("pay.payslip")}</a></div> }]} />
    <Card><div className="row between wrap"><div><h3 style={{ margin: 0 }}>{t("pay.total")}: {money(sh.total)}</h3><p className="hint" style={{ margin: "6px 0 0" }}>{t("pay.rule")}</p></div>
      <div className="row wrap">
        {draft && prepare && <><input className="input" style={{ width: 90 }} inputMode="numeric" value={pct} onChange={(e) => setPct(e.target.value.replace(/\D/g, ""))} aria-label={t("pay.eid_pct")} /><Btn variant="soft" onClick={() => run(`/staff/payroll/sheets/${sh.id}/eid-bonus`, { percent: +pct || 0 })}>{t("pay.eid")}</Btn></>}
        {draft && approve && <Btn onClick={() => run(`/staff/payroll/sheets/${sh.id}/approve`)}>{t("pay.approve")}</Btn>}
        {sh.status === "approved" && prepare && <><select className="input" style={{ width: "auto" }} value={method} onChange={(e) => setMethod(e.target.value)}>{["bank", "cash", "bkash", "nagad"].map((m) => <option key={m} value={m}>{t(`fin.method.${m}`)}</option>)}</select><Btn onClick={() => run(`/staff/payroll/sheets/${sh.id}/pay`, { method }, (r) => t("pay.paid_done", { s: r.sms_sent, f: r.sms_failed }))}>{t("pay.pay")}</Btn></>}
      </div></div>{draft && prepare && <p className="hint">{t("pay.eid_note")}</p>}</Card>
    {ed && <LineModal l={ed} onClose={() => setEd(null)} onDone={() => { setEd(null); onChange(); }} />}
  </div>);
}
function LineModal({ l, onClose, onDone }: { l: Ln; onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [b, setB] = useState(String(l.bonus / 100)); const [d, setD] = useState(String(l.deduction / 100)); const [n, setN] = useState(l.note); const [err, setErr] = useState("");
  const go = async () => { try { await api(`/staff/payroll/lines/${l.id}`, { method: "PUT", body: { bonus: Math.round(+b * 100), deduction: Math.round(+d * 100), note: n } }); onDone(); } catch (e: any) { setErr(e.message); } };
  return <Modal title={`${l.name} · ${money(l.base)}`} onClose={onClose}><div className="grid g2"><Field label={t("pay.bonus") + " (BDT)"}><input className="input" inputMode="decimal" value={b} onChange={(e) => setB(e.target.value)} /></Field><Field label={t("pay.deduction") + " (BDT)"}><input className="input" inputMode="decimal" value={d} onChange={(e) => setD(e.target.value)} /></Field></div>
    <Field label={t("pay.note")}><input className="input" value={n} onChange={(e) => setN(e.target.value)} /></Field>{err && <p className="error">{err}</p>}<div className="row"><Btn onClick={go}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}
function StaffForm({ s, onClose, onDone, onLeave }: { s: Partial<S>; onClose: () => void; onDone: () => void; onLeave: (id: number) => void }) {
  const { t } = useT(); const [f, setF] = useState({ name: s.name ?? "", name_bn: s.name_bn ?? "", role: s.role ?? "guard", phone: s.phone ?? "", salary: String((s.salary ?? 0) / 100), nid: "" }); const [err, setErr] = useState("");
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const go = async () => { try { const body = { ...f, salary: Math.round(+f.salary * 100) }; await api(s.id ? `/staff/${s.id}` : "/staff", { method: s.id ? "PUT" : "POST", body }); onDone(); } catch (e: any) { setErr(e.message); } };
  return <Modal title={s.id ? t("staff.edit") : t("staff.add")} onClose={onClose}>
    <Field label={t("staff.name")}><input className="input" value={f.name} onChange={set("name")} /></Field><Field label={t("staff.name_bn")}><input className="input" value={f.name_bn} onChange={set("name_bn")} /></Field>
    <div className="grid g2"><Field label={t("staff.role")}><select className="input" value={f.role} onChange={set("role")}>{ROLES.map((r) => <option key={r} value={r}>{t(`staff.role.${r}`)}</option>)}</select></Field><Field label={t("staff.phone")}><input className="input" inputMode="tel" value={f.phone} onChange={set("phone")} /></Field>
      <Field label={t("staff.salary")}><input className="input" inputMode="decimal" value={f.salary} onChange={set("salary")} /></Field><Field label={t("staff.nid")} hint={t("staff.nid_hint")}><input className="input" inputMode="numeric" value={f.nid} onChange={set("nid")} /></Field></div>
    {err && <p className="error" role="alert">{err}</p>}<div className="row between"><div className="row"><Btn onClick={go} disabled={f.name.trim().length < 2}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div>{s.id && <Btn variant="danger" onClick={() => confirm(t("staff.leave_confirm", { n: s.name ?? "" })) && onLeave(s.id!)}>{t("staff.leave")}</Btn>}</div></Modal>;
}
function NidModal({ s, onClose }: { s: S; onClose: () => void }) {
  const { t } = useT(); const [full, setFull] = useState(""); const [views, setViews] = useState<{ viewer: string; at: string }[]>([]);
  const show = async () => { const r = await api<{ nid: string }>(`/staff/${s.id}/reveal-nid`, { method: "POST" }); setFull(r.nid); setViews(await api(`/staff/${s.id}/nid-views`)); };
  useEffect(() => { api<{ viewer: string; at: string }[]>(`/staff/${s.id}/nid-views`).then(setViews); }, [s.id]);
  return <Modal title={`${t("staff.nid")} · ${s.name}`} onClose={onClose}><div style={{ fontSize: 26, fontWeight: 800, letterSpacing: 2, margin: "6px 0 12px" }}>{full || s.nid}</div>{!full && <><p className="hint">{t("staff.reveal_note")}</p><Btn onClick={show}>{t("staff.reveal")}</Btn></>}
    <h3 style={{ margin: "18px 0 6px" }}>{t("staff.nid_views")}</h3>{views.length === 0 ? <p className="muted small">{t("staff.nid_none")}</p> : views.slice(0, 6).map((v, i) => <div key={i} className="row between small" style={{ padding: "4px 0", borderTop: "1px solid var(--line)" }}><span>{v.viewer}</span><span className="muted">{ftime(v.at)}</span></div>)}</Modal>;
}
function NewSheetModal({ onClose, onDone }: { onClose: () => void; onDone: (id: number) => void }) {
  const { t } = useT(); const d = new Date(); const [p, setP] = useState(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`); const [err, setErr] = useState("");
  const go = async () => { try { const r = await api<{ id: number }>("/staff/payroll/sheets", { body: { period: p } }); onDone(r.id); } catch (e: any) { setErr(e.message); } };
  return <Modal title={t("pay.sheet_new")} onClose={onClose}><Field label={t("pay.month")}><input className="input" value={p} onChange={(e) => setP(e.target.value)} /></Field>{err && <p className="error">{err}</p>}<div className="row"><Btn onClick={go}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}
