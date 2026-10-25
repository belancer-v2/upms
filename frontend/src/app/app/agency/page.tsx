"use client";
import { useCallback, useEffect, useState } from "react";
import { Btn, Card, Chip, DataTable, Field, Modal, PageHead, Stat, Tabs, useToast } from "@/components/ui";
import { Pager } from "@/components/pager";
import { api, fdate, money } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type Ag = { id: number; name: string; name_bn: string; kind: string; trade_licence: string; reg_no: string; psc_licence: string; address: string; contact_name: string; contact_phone: string; emergency_phone: string;
  contract_start: string | null; contract_end: string | null; days_left: number | null; notice_days: number; sla_notes: string; status: string; expiring: boolean; expired: boolean; fee_mode?: string; monthly_fee?: number; staff?: number; posts?: number; docs?: Doc[] };
type Doc = { id: number; kind: string; filename: string; size: number; content_type: string; at: string };
type Post = { id: number; name: string; name_bn: string; kind: string; headcount: number; shift_ids: number[]; agency_id: number | null; active: boolean };
type Shift = { id: number; name: string; name_bn: string; start: string; end: string; hours: number; active: boolean };
type Slot = { id: number; date: string; post_id: number; shift_id: number; staff_id: number; name: string; name_bn: string; role: string; agency_id: number | null; agency: string; agency_bn: string; status: string; substitute: boolean; note: string; post?: string; post_bn?: string; now?: boolean };
type Warn = { staff_id: number; name: string; name_bn: string; date: string; type: string };
type Person = { id: number; name: string; name_bn: string; role: string; agency_id: number | null; agency: string };
type Roster = { start: string; end: string; days: string[]; posts: Post[]; shifts: Shift[]; slots: Slot[]; warnings: Warn[]; can_edit: boolean; staff: Person[] };
type TabId = "roster" | "today" | "agencies" | "posts" | "attendance" | "bills";
const STATUS_TONE: Record<string, "ok" | "warn" | "bad" | "info" | "mute"> = { planned: "mute", present: "ok", late: "warn", absent: "bad", leave: "info" };
const addDays = (iso: string, n: number) => { const d = new Date(iso + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const dayName = (iso: string, lang: string) => new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short", timeZone: "UTC" });

export default function AgencyPage() {
  const { t } = useT(); const { prop, has } = useAuth();
  const view = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY", "TREASURER", "MEMBER", "AUDITOR", "CARETAKER");
  const bills = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "TREASURER", "PRESIDENT", "SECRETARY", "AUDITOR");
  const [tab, setTab] = useState<TabId>("roster");
  const items: { id: TabId; label: string }[] = [{ id: "roster", label: t("ag.tab.roster") }, { id: "today", label: t("ag.tab.today") },
    ...(view ? [{ id: "agencies" as TabId, label: t("ag.tab.agencies") }, { id: "posts" as TabId, label: t("ag.tab.posts") }, { id: "attendance" as TabId, label: t("ag.tab.attendance") }] : []),
    ...(bills ? [{ id: "bills" as TabId, label: t("ag.tab.bills") }] : [])];
  if (!prop) return null;
  return (<>
    <PageHead helpKey="agency-roster" title={t("ag.title")} sub={t("ag.sub")} />
    <div style={{ marginBottom: 16, overflowX: "auto" }}><Tabs value={tab} onChange={setTab} items={items} /></div>
    {tab === "roster" && <RosterTab />}
    {tab === "today" && <TodayTab />}
    {tab === "agencies" && view && <AgenciesTab />}
    {tab === "posts" && view && <PostsTab />}
    {tab === "attendance" && view && <AttendanceTab />}
    {tab === "bills" && bills && <BillsTab />}
  </>);
}

/* ---------------- roster */
function RosterTab() {
  const { t, pick, lang } = useT(); const { prop } = useAuth(); const toast = useToast();
  const [start, setStart] = useState(""); const [r, setR] = useState<Roster | null>(null); const [cell, setCell] = useState<{ post: Post; shift: Shift; day: string } | null>(null); const [err, setErr] = useState("");
  const load = useCallback(async (s = start) => { try { const d = await api<Roster>(`/agency/roster${s ? `?start=${s}` : ""}`); setR(d); if (!s) setStart(d.start); setErr(""); } catch (e: any) { setErr(e.message); } }, [start]);
  useEffect(() => { load(); }, [prop?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const go = (s: string) => { setStart(s); load(s); };
  if (err) return <p className="error">{err}</p>; if (!r) return <p className="muted">{t("common.loading")}</p>;
  const cellSlots = (p: Post, sh: Shift, d: string) => r.slots.filter((s) => s.post_id === p.id && s.shift_id === sh.id && s.date === d);
  const warnKey = new Set(r.warnings.map((w) => `${w.staff_id}|${w.date}`));
  const copy = async (mode: "copy" | "autofill") => {
    try {
      if (mode === "autofill") { const p = await api<{ added: number; skipped: number }>("/agency/roster/autofill", { body: { start: r.start, apply: false } }); if (!p.added) { toast.show(t("ag.suggest_none")); return; } if (!confirm(t("ag.suggest_n", { n: p.added, s: p.skipped }))) return; }
      const d = await api<{ added: number }>(`/agency/roster/${mode}`, { body: { start: r.start, apply: true } }); toast.show(t("ag.copied", { n: d.added })); load(r.start);
    } catch (e: any) { toast.show(e.message); }
  };
  return (<div className="stack">
    <div className="row between wrap">
      <div className="row wrap"><Btn variant="ghost" size="sm" onClick={() => go(addDays(r.start, -7))}>← {t("ag.prev_week")}</Btn><b>{t("ag.week_of", { d: fdate(r.start) })}</b><Btn variant="ghost" size="sm" onClick={() => go(addDays(r.start, 7))}>{t("ag.next_week")} →</Btn><Btn variant="ghost" size="sm" onClick={() => go("")}>{t("ag.this_week")}</Btn></div>
      <div className="row wrap">{r.can_edit && <><Btn variant="soft" size="sm" onClick={() => copy("copy")}>{t("ag.copy")}</Btn><Btn variant="soft" size="sm" onClick={() => copy("autofill")}>{t("ag.autofill")}</Btn></>}
        <a className="btn btn-outline btn-sm" href={`/app/roster/print?start=${r.start}`} target="_blank" rel="noreferrer">{t("ag.print")}</a></div></div>
    {r.warnings.length > 0 && <Card style={{ borderColor: "var(--warn)", background: "var(--warn-bg)" }}><b style={{ color: "var(--warn)" }}>{t("ag.warn.title")}</b>
      <ul className="list-dot" style={{ marginTop: 6 }}>{r.warnings.map((w, i) => <li key={i}><span>{t(`ag.warn.${w.type}`, { n: pick(w.name, w.name_bn || w.name) })} <span className="muted small">· {dayName(w.date, lang)}</span></span></li>)}</ul></Card>}
    <div className="table-wrap"><table className="t" style={{ minWidth: 920 }}>
      <thead><tr><th style={{ minWidth: 170 }}>{t("ag.post")} / {t("ag.shift")}</th>{r.days.map((d) => <th key={d} style={{ minWidth: 118 }}>{dayName(d, lang)}</th>)}</tr></thead>
      <tbody>{r.posts.flatMap((p) => r.shifts.filter((sh) => !p.shift_ids.length || p.shift_ids.includes(sh.id)).map((sh) => (
        <tr key={`${p.id}-${sh.id}`}>
          <td><b>{pick(p.name, p.name_bn || p.name)}</b><br /><span className="small muted">{pick(sh.name, sh.name_bn || sh.name)} · {sh.start}–{sh.end}</span></td>
          {r.days.map((d) => { const ss = cellSlots(p, sh, d); const short = ss.filter((s) => s.status !== "absent" && s.status !== "leave").length < p.headcount;
            return (<td key={d} onClick={() => r.can_edit && setCell({ post: p, shift: sh, day: d })} style={{ cursor: r.can_edit ? "pointer" : "default", verticalAlign: "top", background: short ? "var(--surface2)" : undefined }}>
              {ss.map((s) => <div key={s.id} style={{ marginBottom: 4 }}><Chip tone={STATUS_TONE[s.status]}>{warnKey.has(`${s.staff_id}|${s.date}`) ? "⚠ " : ""}{pick(s.name, s.name_bn || s.name)}</Chip>{s.substitute && <span className="tiny muted"> {t("ag.chip_sub")}</span>}</div>)}
              {short && <span className="tiny muted">{ss.length ? t("ag.need", { n: p.headcount - ss.filter((s) => s.status !== "absent" && s.status !== "leave").length }) : t("ag.empty_slot")}</span>}</td>); })}
        </tr>)))}</tbody></table></div>
    {cell && <CellModal r={r} cell={cell} slots={cellSlots(cell.post, cell.shift, cell.day)} onClose={() => setCell(null)} onChange={() => load(r.start)} toast={toast.show} />}
    {toast.node}
  </div>);
}

function CellModal({ r, cell, slots, onClose, onChange, toast }: { r: Roster; cell: { post: Post; shift: Shift; day: string }; slots: Slot[]; onClose: () => void; onChange: () => void; toast: (m: string) => void }) {
  const { t, pick, lang } = useT(); const [pickId, setPickId] = useState(""); const [warn, setWarn] = useState<Warn[]>([]); const [sub, setSub] = useState<{ slot: Slot } | null>(null);
  const run = async (fn: () => Promise<any>) => { try { await fn(); onChange(); } catch (e: any) { toast(e.message); } };
  const add = () => run(async () => { const d = await api<{ warnings: Warn[] }>("/agency/roster/slots", { body: { date: cell.day, post_id: cell.post.id, shift_id: cell.shift.id, staff_id: +pickId } }); setWarn(d.warnings); setPickId(""); });
  const mark = (s: Slot, status: string) => run(() => api(`/agency/roster/slots/${s.id}/mark`, { body: { status } }));
  const ask = (s: Slot) => run(async () => { const d = await api<{ sms_status: string }>("/agency/replacements", { body: { slot_id: s.id } }); toast(t("ag.replacement_sent", { s: d.sms_status })); });
  const used = new Set(slots.map((s) => s.staff_id));
  return (<Modal title={t("ag.slot_title", { p: pick(cell.post.name, cell.post.name_bn || cell.post.name), s: pick(cell.shift.name, cell.shift.name_bn || cell.shift.name), d: dayName(cell.day, lang) })} onClose={onClose}>
    {slots.map((s) => (<div key={s.id} className="row between wrap" style={{ padding: "8px 0", borderTop: "1px solid var(--line)" }}>
      <span><b>{pick(s.name, s.name_bn || s.name)}</b> {s.agency ? <Chip tone="info">{pick(s.agency, s.agency_bn || s.agency)}</Chip> : <Chip tone="mute">{t("ag.direct")}</Chip>} {s.substitute && <Chip tone="warn">{t("ag.substitute")}</Chip>} <Chip tone={STATUS_TONE[s.status]}>{t(`ag.st.${s.status}`)}</Chip></span>
      <span className="row wrap" style={{ gap: 6 }}>
        <Btn size="sm" variant="ghost" onClick={() => mark(s, "present")}>{t("ag.st.present")}</Btn><Btn size="sm" variant="ghost" onClick={() => mark(s, "late")}>{t("ag.st.late")}</Btn>
        <Btn size="sm" variant="ghost" onClick={() => mark(s, "absent")}>{t("ag.mark_absent")}</Btn><Btn size="sm" variant="ghost" onClick={() => mark(s, "leave")}>{t("ag.mark_leave")}</Btn>
        {(s.status === "absent" || s.status === "leave") && s.agency_id && <Btn size="sm" variant="soft" onClick={() => ask(s)}>{t("ag.ask_replacement")}</Btn>}
        <Btn size="sm" variant="danger" onClick={() => run(() => api(`/agency/roster/slots/${s.id}`, { method: "DELETE" }))}>{t("ag.remove")}</Btn></span></div>))}
    <div className="row wrap" style={{ marginTop: 12 }}>
      <select className="input" style={{ flex: 1, minWidth: 180 }} value={pickId} onChange={(e) => setPickId(e.target.value)} aria-label={t("ag.pick_person")}><option value="">{t("ag.pick_person")}</option>
        {r.staff.filter((p) => !used.has(p.id)).map((p) => <option key={p.id} value={p.id}>{pick(p.name, p.name_bn || p.name)} · {p.agency || t("ag.direct")}</option>)}</select>
      <Btn onClick={add} disabled={!pickId}>{t("ag.add_person")}</Btn></div>
    {warn.length > 0 && <p className="error" role="alert" style={{ marginTop: 8 }}>{warn.map((w) => t(`ag.warn.${w.type}`, { n: pick(w.name || "", w.name_bn || w.name || "") })).join(" · ")}</p>}
    {slots.some((s) => s.status === "absent" || s.status === "leave") && <div style={{ marginTop: 12 }}><Btn variant="soft" onClick={() => setSub({ slot: slots.find((s) => s.status === "absent" || s.status === "leave")! })}>{t("ag.fulfil")}</Btn></div>}
    {sub && <SubForm slot={sub.slot} onDone={() => { setSub(null); toast(t("ag.sub_done")); onChange(); }} onClose={() => setSub(null)} staff={r.staff} />}
  </Modal>);
}

/** Records the agency's replacement: asks for the request first if none is open, then adds the substitute to the same slot. */
function SubForm({ slot, staff, onDone, onClose }: { slot: Slot; staff: Person[]; onDone: () => void; onClose: () => void }) {
  const { t, pick } = useT(); const [name, setName] = useState(""); const [phone, setPhone] = useState(""); const [existing, setExisting] = useState(""); const [err, setErr] = useState("");
  const go = async () => {
    try {
      const open = await api<{ items: { id: number; slot_id: number; status: string }[] }>("/agency/replacements?size=100"); let rid = open.items.find((x) => x.slot_id === slot.id && x.status === "requested")?.id;
      if (!rid) rid = (await api<{ id: number }>("/agency/replacements", { body: { slot_id: slot.id } })).id;
      await api(`/agency/replacements/${rid}/fulfil`, { body: existing ? { staff_id: +existing } : { new: { name, phone, role: slot.role === "cleaner" ? "cleaner" : "guard", emp_no: "" } } }); onDone();
    } catch (e: any) { setErr(e.message); }
  };
  return (<div style={{ marginTop: 12, borderTop: "1.5px solid var(--line)", paddingTop: 12 }}>
    <div className="grid g2"><Field label={t("ag.sub_name")}><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field><Field label={t("ag.phone")}><input className="input" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} /></Field></div>
    <Field label={t("ag.sub_pick")}><select className="input" value={existing} onChange={(e) => setExisting(e.target.value)}><option value="" />{staff.filter((p) => p.agency_id && p.id !== slot.staff_id).map((p) => <option key={p.id} value={p.id}>{pick(p.name, p.name_bn || p.name)}</option>)}</select></Field>
    {err && <p className="error">{err}</p>}<div className="row"><Btn onClick={go} disabled={!existing && name.trim().length < 2}>{t("ag.fulfil")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></div>);
}

/* ---------------- today */
function TodayTab() {
  const { t, pick } = useT(); const { prop } = useAuth(); const toast = useToast();
  const [d, setD] = useState<{ date: string; items: Slot[]; can_edit: boolean } | null>(null);
  const load = useCallback(() => api<any>("/agency/today").then(setD), []);
  useEffect(() => { load(); }, [load, prop?.id]);
  if (!d) return <p className="muted">{t("common.loading")}</p>;
  const mark = async (s: Slot, status: string) => { try { await api(`/agency/roster/slots/${s.id}/mark`, { body: { status } }); toast.show(t("ag.today.marked")); load(); } catch (e: any) { toast.show(e.message); } };
  const now = d.items.filter((s) => s.now); const pending = d.items.filter((s) => s.status === "planned" && s.date <= d.date);
  const row = (s: Slot) => (<div key={s.id} className="row between wrap" style={{ padding: "10px 0", borderTop: "1px solid var(--line)" }}>
    <span><b>{pick(s.name, s.name_bn || s.name)}</b> <span className="small muted">{pick(s.post ?? "", s.post_bn || s.post)}</span> {s.agency && <Chip tone="info">{pick(s.agency, s.agency_bn || s.agency)}</Chip>} {s.substitute && <Chip tone="warn">{t("ag.substitute")}</Chip>} <Chip tone={STATUS_TONE[s.status]}>{t(`ag.st.${s.status}`)}</Chip></span>
    {d.can_edit && <span className="row" style={{ gap: 6 }}>{(["present", "late", "absent"] as const).map((st) => <Btn key={st} size="sm" variant={s.status === st ? "primary" : "ghost"} onClick={() => mark(s, st)}>{t(`ag.st.${st}`)}</Btn>)}</span>}</div>);
  return (<div className="stack"><div className="grid g3"><Stat label={t("ag.today.on_duty")} value={now.length} /><Stat label={t("ag.st.present")} value={d.items.filter((s) => s.status === "present" || s.status === "late").length} /><Stat label={t("ag.st.absent")} value={d.items.filter((s) => s.status === "absent").length} /></div>
    <Card><div className="row between wrap"><h3 style={{ margin: 0 }}>{t("ag.today.on_duty")}</h3>{d.can_edit && pending.length > 0 && <Btn size="sm" variant="soft" onClick={async () => { for (const s of pending) await api(`/agency/roster/slots/${s.id}/mark`, { body: { status: "present" } }); toast.show(t("ag.today.marked")); load(); }}>{t("ag.today.mark_all")}</Btn>}</div>
      {d.can_edit && <p className="hint">{t("ag.today.tap")}</p>}{now.length ? now.map(row) : <p className="muted small">{t("ag.today.none")}</p>}</Card>
    <Card><h3 style={{ margin: 0 }}>{t("ag.today.all")}</h3>{d.items.filter((s) => s.date === d.date).map(row)}</Card>{toast.node}</div>);
}

/* ---------------- agencies */
function AgenciesTab() {
  const { t, pick } = useT(); const { prop, has } = useAuth(); const toast = useToast(); const edit = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY");
  const [rows, setRows] = useState<Ag[]>([]); const [form, setForm] = useState<Partial<Ag> | null>(null); const [open, setOpen] = useState<Ag | null>(null);
  const load = useCallback(async () => setRows(await api("/agency/agencies")), []);
  useEffect(() => { load(); }, [load, prop?.id]);
  return (<div className="stack">
    <div className="row between wrap"><span /> {edit && <Btn onClick={() => setForm({ kind: "security", fee_mode: "flat", notice_days: 30, status: "active" })}>{t("ag.agency.add")}</Btn>}</div>
    <DataTable rows={rows} pageSize={10} search={(r) => `${r.name} ${r.name_bn} ${r.contact_name}`} cols={[
      { key: "n", head: t("ag.name"), render: (r) => <><b>{pick(r.name, r.name_bn || r.name)}</b><br /><span className="small muted">{t(`ag.kind.${r.kind}`)}</span></> },
      { key: "c", head: t("ag.contact"), render: (r) => <>{r.contact_name}<br /><span className="small muted">{r.contact_phone}</span></> },
      { key: "k", head: t("ag.contract"), render: (r) => <>{r.contract_end ? fdate(r.contract_end) : "–"}{r.expiring && <> <Chip tone="warn">{t("ag.expiring", { n: r.days_left ?? 0 })}</Chip></>}{r.expired && <> <Chip tone="bad">{t("ag.expired", { n: Math.abs(r.days_left ?? 0) })}</Chip></>}</> },
      { key: "f", head: t("ag.fee"), num: true, render: (r) => (r.monthly_fee != null ? <>{money(r.monthly_fee)}<br /><span className="small muted">{t(`ag.fee.${r.fee_mode}`)}</span></> : "–") },
      { key: "s", head: "", render: (r) => <span className="small muted">{t("ag.staff_n", { n: r.staff ?? 0 })} · {t("ag.posts_n", { n: r.posts ?? 0 })}</span> },
      { key: "st", head: "", render: (r) => <Chip tone={r.status === "active" ? "ok" : "mute"}>{t(r.status === "active" ? "ag.active" : "ag.ended")}</Chip> },
      { key: "a", head: "", render: (r) => <span className="row" style={{ gap: 6 }}><Btn size="sm" variant="soft" onClick={async () => setOpen(await api(`/agency/agencies/${r.id}`))}>{t("common.view")}</Btn>{edit && <Btn size="sm" variant="ghost" onClick={() => setForm(r)}>{t("common.edit")}</Btn>}</span> }]} />
    {form && <AgencyForm a={form} onClose={() => setForm(null)} onDone={() => { setForm(null); toast.show(t("ag.saved")); load(); }} />}
    {open && <AgencyDetail a={open} edit={edit} onClose={() => { setOpen(null); load(); }} />}
    {toast.node}</div>);
}

function AgencyForm({ a, onClose, onDone }: { a: Partial<Ag>; onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [err, setErr] = useState("");
  const [f, setF] = useState({ name: a.name ?? "", name_bn: a.name_bn ?? "", kind: a.kind ?? "security", trade_licence: a.trade_licence ?? "", reg_no: a.reg_no ?? "", psc_licence: a.psc_licence ?? "", address: a.address ?? "", contact_name: a.contact_name ?? "",
    contact_phone: a.contact_phone ?? "", emergency_phone: a.emergency_phone ?? "", contract_start: a.contract_start ?? "", contract_end: a.contract_end ?? "", fee_mode: a.fee_mode ?? "flat", fee: String((a.monthly_fee ?? 0) / 100), notice_days: String(a.notice_days ?? 30), sla_notes: a.sla_notes ?? "", status: a.status ?? "active" });
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  const go = async () => { try { const { fee, ...rest } = f; await api(a.id ? `/agency/agencies/${a.id}` : "/agency/agencies", { method: a.id ? "PUT" : "POST", body: { ...rest, monthly_fee: Math.round(+fee * 100), notice_days: +f.notice_days || 0, contract_start: f.contract_start || null, contract_end: f.contract_end || null } }); onDone(); } catch (e: any) { setErr(e.message); } };
  const inp = (k: keyof typeof f, label: string, type = "text") => <Field label={label}><input className="input" type={type} value={f[k]} onChange={set(k)} /></Field>;
  return (<Modal title={a.id ? t("ag.agency.edit") : t("ag.agency.add")} onClose={onClose}>
    <div className="grid g2">{inp("name", t("ag.name"))}{inp("name_bn", t("ag.name_bn"))}
      <Field label={t("ag.kind")}><select className="input" value={f.kind} onChange={set("kind")}>{["security", "cleaning", "both"].map((k) => <option key={k} value={k}>{t(`ag.kind.${k}`)}</option>)}</select></Field>
      <Field label={t("ag.status")}><select className="input" value={f.status} onChange={set("status")}><option value="active">{t("ag.active")}</option><option value="ended">{t("ag.ended")}</option></select></Field>
      {inp("trade_licence", t("ag.trade"))}{inp("reg_no", t("ag.reg"))}{inp("psc_licence", t("ag.psc"))}{inp("address", t("ag.address"))}
      {inp("contact_name", t("ag.contact"))}{inp("contact_phone", t("ag.phone"))}{inp("emergency_phone", t("ag.emergency"))}<span />
      {inp("contract_start", t("ag.c_start"), "date")}{inp("contract_end", t("ag.c_end"), "date")}
      <Field label={t("ag.fee_mode")}><select className="input" value={f.fee_mode} onChange={set("fee_mode")}><option value="flat">{t("ag.fee.flat")}</option><option value="per_post">{t("ag.fee.per_post")}</option></select></Field>{inp("fee", t("ag.fee"))}
      {inp("notice_days", t("ag.notice"))}</div>
    <Field label={t("ag.sla")}><textarea className="input" rows={3} value={f.sla_notes} onChange={set("sla_notes")} /></Field>
    {err && <p className="error" role="alert">{err}</p>}<div className="row"><Btn onClick={go} disabled={f.name.trim().length < 2}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>);
}

function AgencyDetail({ a: first, edit, onClose }: { a: Ag; edit: boolean; onClose: () => void }) {
  const { t, pick } = useT(); const [a, setA] = useState(first); const [kind, setKind] = useState("licence"); const [err, setErr] = useState(""); const [staff, setStaff] = useState<any[]>([]); const [add, setAdd] = useState(false);
  const reload = useCallback(async () => { setA(await api(`/agency/agencies/${first.id}`)); setStaff((await api<any[]>("/staff?employer=" + first.id).catch(() => [])) as any[]); }, [first.id]);
  useEffect(() => { reload(); }, [reload]);
  const upload = async (file: File) => {
    setErr(""); const fd = new FormData(); fd.append("kind", kind); fd.append("file", file);
    const res = await fetch(`/api/agency/agencies/${a.id}/docs`, { method: "POST", headers: { Authorization: `Bearer ${localStorage.getItem("fw_token") ?? ""}`, "X-Property-Id": localStorage.getItem("fw_prop") ?? "0" }, body: fd });
    if (!res.ok) { let m = res.statusText; try { m = (await res.json()).detail ?? m; } catch {} setErr(String(m)); return; } reload();
  };
  const open = async (d: Doc) => { const res = await fetch(`/api/agency/agencies/${a.id}/docs/${d.id}`, { headers: { Authorization: `Bearer ${localStorage.getItem("fw_token") ?? ""}`, "X-Property-Id": localStorage.getItem("fw_prop") ?? "0" } }); if (res.ok) window.open(URL.createObjectURL(await res.blob()), "_blank"); };
  const info = (k: string, v: React.ReactNode) => <div className="row between" style={{ padding: "6px 0", borderTop: "1px solid var(--line)" }}><span className="muted small">{k}</span><span style={{ textAlign: "right" }}>{v || "–"}</span></div>;
  return (<Modal title={pick(a.name, a.name_bn || a.name)} onClose={onClose}>
    {info(t("ag.kind"), t(`ag.kind.${a.kind}`))}{info(t("ag.trade"), a.trade_licence)}{info(t("ag.reg"), a.reg_no)}{a.kind !== "cleaning" && info(t("ag.psc"), a.psc_licence)}{info(t("ag.address"), a.address)}
    {info(t("ag.contact"), `${a.contact_name} ${a.contact_phone}`)}{info(t("ag.emergency"), a.emergency_phone)}{info(t("ag.contract"), `${a.contract_start ? fdate(a.contract_start) : "–"} → ${a.contract_end ? fdate(a.contract_end) : "–"}`)}
    {a.monthly_fee != null && info(t("ag.fee"), `${money(a.monthly_fee)} · ${t(`ag.fee.${a.fee_mode}`)}`)}{info(t("ag.notice"), a.notice_days)}{info(t("ag.sla"), a.sla_notes)}
    <h3 style={{ margin: "16px 0 6px" }}>{t("ag.people")} · {staff.length}</h3>
    {staff.map((s) => <div key={s.id} className="row between small" style={{ padding: "4px 0", borderTop: "1px solid var(--line)" }}><span>{pick(s.name, s.name_bn || s.name)} {s.agency?.substitute && <Chip tone="warn">{t("ag.chip_sub")}</Chip>}</span><span className="muted">{s.agency?.emp_no} · <code>{s.nid}</code></span></div>)}
    {edit && <div style={{ marginTop: 8 }}><Btn size="sm" variant="soft" onClick={() => setAdd(true)}>{t("ag.person.add")}</Btn></div>}
    <h3 style={{ margin: "16px 0 6px" }}>{t("ag.docs")}</h3>
    {(a.docs ?? []).length === 0 ? <p className="muted small">{t("ag.doc.none")}</p> : a.docs!.map((d) => <div key={d.id} className="row between small" style={{ padding: "4px 0", borderTop: "1px solid var(--line)" }}><span><b>{t(`ag.doc.${d.kind}`)}</b> · {d.filename} <span className="muted">({Math.round(d.size / 1024)} KB)</span></span>
      <span className="row" style={{ gap: 6 }}><Btn size="sm" variant="ghost" onClick={() => open(d)}>{t("ag.doc.open")}</Btn>{edit && <Btn size="sm" variant="ghost" onClick={async () => { if (confirm(t("ag.doc.delete"))) { await api(`/agency/agencies/${a.id}/docs/${d.id}`, { method: "DELETE" }); reload(); } }}>{t("common.delete")}</Btn>}</span></div>)}
    {edit && <div className="row wrap" style={{ marginTop: 10 }}><select className="input" style={{ width: "auto" }} value={kind} onChange={(e) => setKind(e.target.value)}>{["licence", "contract", "insurance", "police_verification"].map((k) => <option key={k} value={k}>{t(`ag.doc.${k}`)}</option>)}</select>
      <input type="file" accept="application/pdf,image/jpeg,image/png" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} aria-label={t("ag.doc.upload")} /></div>}
    {edit && <p className="hint">{t("ag.doc.hint")}</p>}{err && <p className="error" role="alert">{err}</p>}
    {add && <AgencyStaffForm agencyId={a.id} onClose={() => setAdd(false)} onDone={() => { setAdd(false); reload(); }} />}</Modal>);
}

function AgencyStaffForm({ agencyId, onClose, onDone }: { agencyId: number; onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [f, setF] = useState({ name: "", name_bn: "", role: "guard", phone: "", nid: "", emp_no: "", deployed_on: "" }); const [err, setErr] = useState("");
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const go = async () => { try { await api(`/agency/agencies/${agencyId}/staff`, { body: { ...f, deployed_on: f.deployed_on || null } }); onDone(); } catch (e: any) { setErr(e.message); } };
  return (<Modal title={t("ag.person.add")} onClose={onClose}><div className="grid g2">
    <Field label={t("ag.sub_name")}><input className="input" value={f.name} onChange={set("name")} /></Field><Field label={t("ag.name_bn")}><input className="input" value={f.name_bn} onChange={set("name_bn")} /></Field>
    <Field label={t("ag.job")}><select className="input" value={f.role} onChange={set("role")}>{["guard", "cleaner", "caretaker", "other"].map((r) => <option key={r} value={r}>{t(`ag.role.${r}`)}</option>)}</select></Field><Field label={t("ag.phone")}><input className="input" inputMode="tel" value={f.phone} onChange={set("phone")} /></Field>
    <Field label={t("ag.nid")}><input className="input" inputMode="numeric" value={f.nid} onChange={set("nid")} /></Field><Field label={t("ag.emp_no")}><input className="input" value={f.emp_no} onChange={set("emp_no")} /></Field>
    <Field label={t("ag.deployed")}><input className="input" type="date" value={f.deployed_on} onChange={set("deployed_on")} /></Field></div>
    {err && <p className="error" role="alert">{err}</p>}<div className="row"><Btn onClick={go} disabled={f.name.trim().length < 2}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>);
}

/* ---------------- posts and shifts */
function PostsTab() {
  const { t, pick } = useT(); const { prop, has } = useAuth(); const toast = useToast(); const edit = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "SECRETARY", "CARETAKER");
  const [d, setD] = useState<{ posts: Post[]; shifts: Shift[] } | null>(null); const [ags, setAgs] = useState<Ag[]>([]); const [pf, setPf] = useState<Partial<Post> | null>(null); const [sf, setSf] = useState<Partial<Shift> | null>(null);
  const load = useCallback(async () => { setD(await api("/agency/posts")); setAgs(await api("/agency/agencies")); }, []);
  useEffect(() => { load(); }, [load, prop?.id]);
  if (!d) return <p className="muted">{t("common.loading")}</p>;
  return (<div className="stack">
    <Card><div className="row between wrap"><h3 style={{ margin: 0 }}>{t("ag.posts.title")}</h3>{edit && <Btn size="sm" onClick={() => setPf({ kind: "security", headcount: 1, shift_ids: [], active: true })}>{t("ag.post.add")}</Btn>}</div>
      <DataTable rows={d.posts} pageSize={10} cols={[{ key: "n", head: t("ag.post.name"), render: (r) => <><b>{pick(r.name, r.name_bn || r.name)}</b> {!r.active && <Chip tone="mute">{t("ag.post.inactive")}</Chip>}</> }, { key: "k", head: t("ag.post.kind"), render: (r) => t(`ag.kind.${r.kind}`) },
        { key: "h", head: t("ag.post.headcount"), num: true, render: (r) => r.headcount }, { key: "s", head: t("ag.post.shifts"), render: (r) => (r.shift_ids.length ? d.shifts.filter((s) => r.shift_ids.includes(s.id)).map((s) => pick(s.name, s.name_bn || s.name)).join(", ") : t("ag.post.all_shifts")) },
        { key: "a", head: t("ag.post.agency"), render: (r) => { const a = ags.find((x) => x.id === r.agency_id); return a ? pick(a.name, a.name_bn || a.name) : t("ag.post.direct"); } },
        { key: "e", head: "", render: (r) => edit && <Btn size="sm" variant="ghost" onClick={() => setPf(r)}>{t("common.edit")}</Btn> }]} /></Card>
    <Card><div className="row between wrap"><h3 style={{ margin: 0 }}>{t("ag.shifts.title")}</h3>{edit && <Btn size="sm" onClick={() => setSf({ start: "06:00", end: "14:00", active: true })}>{t("ag.shift.add")}</Btn>}</div>
      <DataTable rows={d.shifts} pageSize={10} cols={[{ key: "n", head: t("ag.shift.name"), render: (r) => <b>{pick(r.name, r.name_bn || r.name)}</b> }, { key: "s", head: t("ag.shift.start"), render: (r) => r.start }, { key: "e", head: t("ag.shift.end"), render: (r) => r.end },
        { key: "h", head: "", render: (r) => t("ag.shift.hours", { h: r.hours }) }, { key: "x", head: "", render: (r) => edit && <Btn size="sm" variant="ghost" onClick={() => setSf(r)}>{t("common.edit")}</Btn> }]} /></Card>
    {pf && <PostForm p={pf} shifts={d.shifts} ags={ags} onClose={() => setPf(null)} onDone={() => { setPf(null); toast.show(t("ag.saved")); load(); }} />}
    {sf && <ShiftForm s={sf} onClose={() => setSf(null)} onDone={() => { setSf(null); toast.show(t("ag.saved")); load(); }} />}{toast.node}</div>);
}

function PostForm({ p, shifts, ags, onClose, onDone }: { p: Partial<Post>; shifts: Shift[]; ags: Ag[]; onClose: () => void; onDone: () => void }) {
  const { t, pick } = useT(); const [f, setF] = useState({ name: p.name ?? "", name_bn: p.name_bn ?? "", kind: p.kind ?? "security", headcount: String(p.headcount ?? 1), shift_ids: p.shift_ids ?? [], agency_id: p.agency_id ? String(p.agency_id) : "", active: p.active ?? true }); const [err, setErr] = useState("");
  const go = async (over: object = {}) => { try { await api(p.id ? `/agency/posts/${p.id}` : "/agency/posts", { method: p.id ? "PUT" : "POST", body: { ...f, ...over, headcount: +f.headcount || 1, agency_id: f.agency_id ? +f.agency_id : null } }); onDone(); } catch (e: any) { setErr(e.message); } };
  return (<Modal title={p.id ? t("ag.post.edit") : t("ag.post.add")} onClose={onClose}><div className="grid g2">
    <Field label={t("ag.post.name")}><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field><Field label={t("ag.name_bn")}><input className="input" value={f.name_bn} onChange={(e) => setF({ ...f, name_bn: e.target.value })} /></Field>
    <Field label={t("ag.post.kind")}><select className="input" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="security">{t("ag.kind.security")}</option><option value="cleaning">{t("ag.kind.cleaning")}</option></select></Field>
    <Field label={t("ag.post.headcount")}><input className="input" inputMode="numeric" value={f.headcount} onChange={(e) => setF({ ...f, headcount: e.target.value.replace(/\D/g, "") })} /></Field>
    <Field label={t("ag.post.agency")}><select className="input" value={f.agency_id} onChange={(e) => setF({ ...f, agency_id: e.target.value })}><option value="">{t("ag.post.direct")}</option>{ags.filter((a) => a.status === "active").map((a) => <option key={a.id} value={a.id}>{pick(a.name, a.name_bn || a.name)}</option>)}</select></Field>
    <Field label={t("ag.post.shifts")} hint={t("ag.post.all_shifts")}><div className="row wrap">{shifts.map((s) => <label key={s.id} className="row small" style={{ gap: 4 }}><input type="checkbox" checked={f.shift_ids.includes(s.id)} onChange={(e) => setF({ ...f, shift_ids: e.target.checked ? [...f.shift_ids, s.id] : f.shift_ids.filter((x) => x !== s.id) })} />{pick(s.name, s.name_bn || s.name)}</label>)}</div></Field></div>
    {err && <p className="error" role="alert">{err}</p>}<div className="row between"><div className="row"><Btn onClick={() => go()} disabled={f.name.trim().length < 2}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div>{p.id && p.active && <Btn variant="danger" onClick={() => go({ active: false })}>{t("ag.post.off")}</Btn>}</div></Modal>);
}

function ShiftForm({ s, onClose, onDone }: { s: Partial<Shift>; onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [f, setF] = useState({ name: s.name ?? "", name_bn: s.name_bn ?? "", start: s.start ?? "06:00", end: s.end ?? "14:00", active: s.active ?? true }); const [err, setErr] = useState("");
  const go = async () => { try { await api(s.id ? `/agency/shifts/${s.id}` : "/agency/shifts", { method: s.id ? "PUT" : "POST", body: f }); onDone(); } catch (e: any) { setErr(e.message); } };
  return (<Modal title={s.id ? t("ag.shift.edit") : t("ag.shift.add")} onClose={onClose}><div className="grid g2">
    <Field label={t("ag.shift.name")}><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field><Field label={t("ag.name_bn")}><input className="input" value={f.name_bn} onChange={(e) => setF({ ...f, name_bn: e.target.value })} /></Field>
    <Field label={t("ag.shift.start")}><input className="input" type="time" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} /></Field><Field label={t("ag.shift.end")}><input className="input" type="time" value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} /></Field></div>
    {err && <p className="error" role="alert">{err}</p>}<div className="row"><Btn onClick={go} disabled={f.name.trim().length < 2}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>);
}

/* ---------------- attendance */
type Sum = { period: string; staff: { staff_id: number; name: string; name_bn: string; agency: string; emp_no: string; substitute: boolean; scheduled: number; present: number; late: number; absent: number; leave: number }[];
  agencies: { agency_id: number; name: string; name_bn: string; scheduled: number; present: number; late: number; absent: number; leave: number; shortfall_units: number; shortfall_days: number }[] };
type Repl = { id: number; date: string; post: string; post_bn: string; shift: string; shift_bn: string; agency: string; agency_bn: string; absent: string; absent_bn: string; status: string; substitute: string; sms_status: string };
const thisMonth = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };

function AttendanceTab() {
  const { t, pick } = useT(); const { prop, has } = useAuth(); const canFulfil = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "SECRETARY", "CARETAKER"); const [period, setPeriod] = useState(thisMonth()); const [s, setS] = useState<Sum | null>(null); const [err, setErr] = useState("");
  const [rep, setRep] = useState<{ items: Repl[]; total: number; page: number; size: number } | null>(null); const [page, setPage] = useState(1);
  useEffect(() => { if (/^\d{4}-\d{2}$/.test(period)) api<Sum>(`/agency/attendance/summary?period=${period}`).then((d) => { setS(d); setErr(""); }).catch((e) => setErr(e.message)); }, [period, prop?.id]);
  const [ful, setFul] = useState<Repl | null>(null); const [tick, setTick] = useState(0);
  useEffect(() => { api<any>(`/agency/replacements?page=${page}&size=10`).then(setRep).catch(() => {}); }, [page, prop?.id, tick]);
  return (<div className="stack">
    <div className="row wrap"><Field label={t("ag.att.month")}><input className="input" style={{ width: 150 }} value={period} onChange={(e) => setPeriod(e.target.value)} /></Field></div>
    {err && <p className="error">{err}</p>}
    {s && <><h3 style={{ margin: 0 }}>{t("ag.att.agency")}</h3>
      <DataTable rows={s.agencies.map((a) => ({ ...a, id: a.agency_id }))} pageSize={10} cols={[{ key: "n", head: t("ag.bill.agency"), render: (r) => <b>{pick(r.name, r.name_bn || r.name)}</b> }, { key: "s", head: t("ag.att.scheduled"), num: true, render: (r) => r.scheduled },
        { key: "p", head: t("ag.st.present"), num: true, render: (r) => r.present }, { key: "l", head: t("ag.st.late"), num: true, render: (r) => r.late }, { key: "a", head: t("ag.att.absences"), num: true, render: (r) => r.absent }, { key: "v", head: t("ag.st.leave"), num: true, render: (r) => r.leave },
        { key: "u", head: t("ag.att.shortfall"), num: true, render: (r) => <b>{r.shortfall_units}</b> }, { key: "d", head: t("ag.att.shortfall_days"), num: true, render: (r) => r.shortfall_days }]} />
      <h3 style={{ margin: 0 }}>{t("ag.att.people")}</h3>
      <DataTable rows={s.staff.map((p) => ({ ...p, id: p.staff_id }))} pageSize={10} search={(r) => `${r.name} ${r.agency} ${r.emp_no}`} cols={[{ key: "n", head: t("ag.att.person"), render: (r) => <><b>{pick(r.name, r.name_bn || r.name)}</b> {r.substitute && <Chip tone="warn">{t("ag.chip_sub")}</Chip>}<br /><span className="small muted">{r.agency} {r.emp_no}</span></> },
        { key: "s", head: t("ag.att.scheduled"), num: true, render: (r) => r.scheduled }, { key: "p", head: t("ag.st.present"), num: true, render: (r) => r.present }, { key: "l", head: t("ag.st.late"), num: true, render: (r) => r.late },
        { key: "a", head: t("ag.att.absences"), num: true, render: (r) => r.absent }, { key: "v", head: t("ag.st.leave"), num: true, render: (r) => r.leave }]} /></>}
    {rep && rep.items.length > 0 && <Card><h3 style={{ margin: 0 }}>{t("ag.ask_replacement")}</h3>
      {rep.items.map((r) => <div key={r.id} className="row between wrap small" style={{ padding: "6px 0", borderTop: "1px solid var(--line)" }}><span>{fdate(r.date)} · {pick(r.post, r.post_bn || r.post)} · {pick(r.shift, r.shift_bn || r.shift)} · {pick(r.absent, r.absent_bn || r.absent)}</span>
        <span className="row" style={{ gap: 8 }}><Chip tone={r.status === "fulfilled" ? "ok" : "warn"}>{r.status === "fulfilled" ? r.substitute : `SMS: ${r.sms_status}`}</Chip>{canFulfil && r.status !== "fulfilled" && <Btn size="sm" variant="soft" onClick={() => setFul(r)}>{t("ag.fulfil")}</Btn>}</span></div>)}
      <Pager page={rep.page} size={rep.size} total={rep.total} onPage={setPage} /></Card>}
    {ful && <FulfilModal req={ful} onClose={() => setFul(null)} onDone={() => { setFul(null); setPage(1); setTick((n) => n + 1); }} />}
  </div>);
}

/** Shortcut from the attendance list: record who covers an open replacement request without opening the roster cell. */
function FulfilModal({ req, onDone, onClose }: { req: Repl; onDone: () => void; onClose: () => void }) {
  const { t, pick } = useT(); const [name, setName] = useState(""); const [phone, setPhone] = useState(""); const [existing, setExisting] = useState(""); const [role, setRole] = useState("guard"); const [err, setErr] = useState("");
  const [people, setPeople] = useState<{ id: number; name: string; name_bn: string }[]>([]);
  useEffect(() => { api<{ staff: { id: number; name: string; name_bn: string; agency_id: number | null }[] }>("/agency/roster").then((r) => setPeople(r.staff.filter((p) => p.agency_id))).catch(() => {}); }, []);
  const go = async () => { try { await api(`/agency/replacements/${req.id}/fulfil`, { body: existing ? { staff_id: +existing } : { new: { name, phone, role, emp_no: "" } } }); onDone(); } catch (e: any) { setErr(e.message); } };
  return (<Modal title={t("ag.fulfil")} onClose={onClose}>
    <p className="small muted">{fdate(req.date)} · {pick(req.post, req.post_bn || req.post)} · {pick(req.shift, req.shift_bn || req.shift)} · {pick(req.absent, req.absent_bn || req.absent)}</p>
    <Field label={t("ag.sub_pick")}><select className="input" value={existing} onChange={(e) => setExisting(e.target.value)}><option value="" />{people.map((p) => <option key={p.id} value={p.id}>{pick(p.name, p.name_bn || p.name)}</option>)}</select></Field>
    {!existing && <div className="grid g2"><Field label={t("ag.sub_name")}><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field><Field label={t("ag.phone")}><input className="input" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} /></Field>
      <Field label={t("staff.role")}><select className="input" value={role} onChange={(e) => setRole(e.target.value)}><option value="guard">{t("staff.role.guard")}</option><option value="cleaner">{t("staff.role.cleaner")}</option></select></Field></div>}
    {err && <p className="error" role="alert">{err}</p>}<div className="row"><Btn onClick={go} disabled={!existing && name.trim().length < 2}>{t("ag.fulfil")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>);
}

/* ---------------- bills */
type Chk = { contract: number; rate: number; shortfall_units: number; deduction: number; expected: number; days: { date: string; post_id: number; shift_id: number; required: number; present: number; short: number }[] };
type Bill = { id: number; agency: string; agency_bn: string; period: string; number: string; amount: number; expected: number; shortfall_units: number; deduction: number; variance: number; status: string; approvals: number; approvals_needed: number; note: string };

function BillsTab() {
  const { t, pick } = useT(); const { prop, has } = useAuth(); const toast = useToast(); const record = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "TREASURER"); const setRate = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY", "TREASURER");
  const [ags, setAgs] = useState<Ag[]>([]); const [aid, setAid] = useState(""); const [period, setPeriod] = useState(thisMonth()); const [chk, setChk] = useState<Chk | null>(null); const [page, setPage] = useState(1);
  const [list, setList] = useState<{ items: Bill[]; total: number; page: number; size: number } | null>(null); const [num, setNum] = useState(""); const [amt, setAmt] = useState(""); const [note, setNote] = useState(""); const [rate, setRateV] = useState(""); const [err, setErr] = useState("");
  const loadList = useCallback(() => api<any>(`/agency/bills?page=${page}&size=10`).then(setList), [page]);
  useEffect(() => { api<Ag[]>("/agency/agencies").then((a) => { setAgs(a); if (a[0]) setAid(String(a[0].id)); }); api<{ shortfall_rate: number }>("/agency/settings").then((s) => setRateV(String(s.shortfall_rate / 100))); }, [prop?.id]);
  useEffect(() => { loadList(); }, [loadList, prop?.id]);
  useEffect(() => { if (aid && /^\d{4}-\d{2}$/.test(period)) api<Chk>(`/agency/bills/check?agency_id=${aid}&period=${period}`).then((c) => { setChk(c); setAmt(String(c.expected / 100)); setErr(""); }).catch((e) => setErr(e.message)); }, [aid, period, prop?.id]);
  const save = async () => { try { await api("/agency/bills", { body: { agency_id: +aid, period, number: num, amount: Math.round(+amt * 100), note } }); toast.show(t("ag.bill.recorded")); setNum(""); setNote(""); loadList(); } catch (e: any) { setErr(e.message); } };
  const saveRate = async () => { try { await api("/agency/settings", { method: "PUT", body: { shortfall_rate: Math.round(+rate * 100) } }); toast.show(t("ag.saved")); if (aid) setChk(await api(`/agency/bills/check?agency_id=${aid}&period=${period}`)); } catch (e: any) { toast.show(e.message); } };
  const diff = (v: number) => (v === 0 ? <Chip tone="ok">{t("ag.bill.match")}</Chip> : <Chip tone={v > 0 ? "bad" : "info"}>{v > 0 ? t("ag.bill.over") : t("ag.bill.under")} {money(Math.abs(v))}</Chip>);
  return (<div className="stack">
    <Card><h3 style={{ margin: 0 }}>{t("ag.bill.check")}</h3>
      <div className="grid g3" style={{ marginTop: 10 }}><Field label={t("ag.bill.agency")}><select className="input" value={aid} onChange={(e) => setAid(e.target.value)}><option value="">{t("ag.bill.pick")}</option>{ags.map((a) => <option key={a.id} value={a.id}>{pick(a.name, a.name_bn || a.name)}</option>)}</select></Field>
        <Field label={t("ag.bill.month")}><input className="input" value={period} onChange={(e) => setPeriod(e.target.value)} /></Field></div>
      {chk && <><div className="grid g3"><Stat label={t("ag.bill.contract")} value={money(chk.contract)} /><Stat label={t("ag.bill.deduct")} value={`− ${money(chk.deduction)}`} note={t("ag.bill.n_missing", { n: chk.shortfall_units, r: money(chk.rate) })} /><Stat label={t("ag.bill.expected")} value={money(chk.expected)} /></div>
        {chk.days.length > 0 && <p className="small muted" style={{ marginTop: 10 }}>{t("ag.bill.days")}: {Array.from(new Set(chk.days.map((d) => d.date))).map((d) => fdate(d)).join(", ")}</p>}</>}
      {setRate && <div className="row wrap" style={{ marginTop: 12, alignItems: "end" }}><Field label={t("ag.settings")} hint={t("ag.settings_hint")}><input className="input" style={{ width: 160 }} inputMode="decimal" value={rate} onChange={(e) => setRateV(e.target.value)} /></Field><Btn size="sm" variant="soft" onClick={saveRate}>{t("common.save")}</Btn></div>}
      {record && aid && <div style={{ marginTop: 12, borderTop: "1.5px solid var(--line)", paddingTop: 12 }}><div className="grid g3"><Field label={t("ag.bill.number")}><input className="input" value={num} onChange={(e) => setNum(e.target.value)} /></Field>
        <Field label={t("ag.bill.amount")}><input className="input" inputMode="decimal" value={amt} onChange={(e) => setAmt(e.target.value)} /></Field><Field label={t("ag.bill.note")}><input className="input" value={note} onChange={(e) => setNote(e.target.value)} /></Field></div>
        <p className="hint">{t("ag.bill.rule")}</p>{err && <p className="error" role="alert">{err}</p>}<Btn onClick={save} disabled={!num.trim() || !(+amt > 0)}>{t("ag.bill.record")}</Btn></div>}
    </Card>
    {list && <><DataTable rows={list.items} pageSize={100} cols={[{ key: "a", head: t("ag.bill.agency"), render: (r) => <b>{pick(r.agency, r.agency_bn || r.agency)}</b> }, { key: "p", head: t("ag.bill.month"), render: (r) => r.period }, { key: "n", head: t("ag.bill.number"), render: (r) => r.number },
      { key: "e", head: t("ag.bill.expected"), num: true, render: (r) => money(r.expected) }, { key: "m", head: t("ag.bill.amount"), num: true, render: (r) => <b>{money(r.amount)}</b> }, { key: "v", head: t("ag.bill.variance"), render: (r) => diff(r.variance) },
      { key: "s", head: t("ag.bill.expense"), render: (r) => <Chip tone={r.status === "paid" ? "ok" : r.status === "rejected" ? "bad" : "warn"}>{t(`ag.bill.st.${r.status}`)}{r.status === "pending" && r.approvals_needed > 1 ? ` ${r.approvals}/${r.approvals_needed}` : ""}</Chip> }]} />
      <Pager page={list.page} size={list.size} total={list.total} onPage={setPage} /></>}
    {toast.node}</div>);
}
