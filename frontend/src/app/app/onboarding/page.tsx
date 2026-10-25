"use client";
import { useCallback, useEffect, useState } from "react";
import { Btn, Card, Chip, DataTable, Field, Modal, PageHead, Stat, useToast } from "@/components/ui";
import { api, fdate, ftime, money, store } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type Miss = { fields: string[]; docs: string[]; docs_open: string[] };
type C = { id: number; unit_id: number; unit: string; status: string; name: string; phone: string; rent: number; advance: number; start_date: string; lease_months: number; police_ref: string; police_on: string | null; receipt_no: string; missing: Miss; nid: string;
  details?: Record<string, any>; docs?: D[]; events?: { at: string; by: string; key: string; note: string }[]; token?: string };
type D = { id: number; kind: string; filename: string; size: number; status: string; note: string };
type U = { id: number; number: string; status: string };
const STEPS = ["invited", "review", "verified", "police", "done"];
const tone = (s: string) => (s === "done" ? "ok" : s === "cancelled" ? "bad" : s === "verified" || s === "police" ? "info" : "warn") as "ok" | "bad" | "info" | "warn";
const DOCS = ["nid_front", "nid_back", "photo", "agreement", "noc", "employer"];

export default function Onboarding() {
  const { t } = useT(); const { prop, has } = useAuth(); const toast = useToast();
  const [rows, setRows] = useState<C[] | null>(null); const [open, setOpen] = useState<C | null>(null); const [form, setForm] = useState(false);
  const can = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "FLAT_OWNER", "OWNER_REP");
  const load = useCallback(() => api<C[]>("/onboarding/cases").then(setRows), []);
  useEffect(() => { load(); }, [load, prop?.id]);
  if (!rows) return <p className="muted">{t("common.loading")}</p>;
  const n = (s: string) => rows.filter((r) => r.status === s).length;
  const show = async (c: C) => setOpen(await api<C>(`/onboarding/cases/${c.id}`));
  return (<>
    <PageHead helpKey="tenant-onboarding" title={t("ob.title")} sub={t("ob.sub")} actions={can && <Btn onClick={() => setForm(true)}>{t("ob.new")}</Btn>} />
    <div className="grid g4" style={{ marginBottom: 16 }}>{(["invited", "review", "verified", "police"] as const).map((s) => <Stat key={s} label={t(`ob.st.${s}`)} value={n(s)} />)}</div>
    <DataTable rows={rows} pageSize={10} search={(r) => `${r.name} ${r.unit}`} cols={[
      { key: "u", head: t("ob.f.unit"), render: (r) => <b>{r.unit}</b> }, { key: "n", head: t("common.name"), render: (r) => <>{r.name}<br /><span className="small muted">{r.phone}</span></> },
      { key: "r", head: t("ob.rent"), num: true, render: (r) => money(r.rent) }, { key: "s", head: t("ob.start"), render: (r) => <span className="nowrap">{fdate(r.start_date)}</span> },
      { key: "st", head: t("common.status"), render: (r) => <Chip tone={tone(r.status)}>{t(`ob.st.${r.status}`)}</Chip> }, { key: "a", head: "", render: (r) => <Btn size="sm" variant="soft" onClick={() => show(r)}>{t("common.view")}</Btn> }]} />
    {form && <NewCase onClose={() => setForm(false)} onDone={() => { setForm(false); toast.show(t("ob.created")); load(); }} />}
    {open && <Detail c={open} onClose={() => { setOpen(null); load(); }} onChange={(c) => { setOpen(c); load(); }} toast={toast.show} />}
    {toast.node}
  </>);
}

function NewCase({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [units, setUnits] = useState<U[]>([]); const [err, setErr] = useState("");
  const [f, setF] = useState({ unit_id: "", name: "", phone: "", rent: "", advance: "", start_date: "", lease_months: "12" });
  useEffect(() => { api<U[]>("/units").then((u) => setUnits(u.filter((x) => x.status === "to_let" || x.status === "vacant"))); }, []);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const go = async () => { try { await api("/onboarding/cases", { body: { unit_id: +f.unit_id, name: f.name, phone: f.phone, rent: Math.round(+f.rent * 100), advance: Math.round(+f.advance * 100), start_date: f.start_date, lease_months: +f.lease_months } }); onDone(); } catch (e: any) { setErr(e.message); } };
  return <Modal title={t("ob.new")} onClose={onClose}>
    <Field label={t("ob.f.unit")}><select className="input" value={f.unit_id} onChange={set("unit_id")}><option value="">{t("ob.f.pick_unit")}</option>{units.map((u) => <option key={u.id} value={u.id}>{u.number} · {t(`unit.status.${u.status}`)}</option>)}</select></Field>
    {units.length === 0 && <p className="hint">{t("ob.no_units")}</p>}
    <div className="grid g2"><Field label={t("ob.f.name")}><input className="input" value={f.name} onChange={set("name")} /></Field><Field label={t("ob.f.phone")}><input className="input" inputMode="tel" value={f.phone} onChange={set("phone")} /></Field>
      <Field label={t("ob.f.rent")}><input className="input" inputMode="decimal" value={f.rent} onChange={set("rent")} /></Field><Field label={t("ob.f.advance")}><input className="input" inputMode="decimal" value={f.advance} onChange={set("advance")} /></Field>
      <Field label={t("ob.f.start")}><input className="input" type="date" value={f.start_date} onChange={set("start_date")} /></Field><Field label={t("ob.f.lease")}><input className="input" type="number" min={1} value={f.lease_months} onChange={set("lease_months")} /></Field></div>
    <p className="hint">{t("ob.f.note")}</p>{err && <p className="error" role="alert">{err}</p>}
    <div className="row"><Btn onClick={go} disabled={!f.unit_id || f.name.trim().length < 2 || f.phone.trim().length < 6 || !f.start_date}>{t("ob.new")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}

function Detail({ c, onClose, onChange, toast }: { c: C; onClose: () => void; onChange: (c: C) => void; toast: (m: string) => void }) {
  const { t } = useT(); const { has } = useAuth(); const review = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "SECRETARY"); const [sub, setSub] = useState<"" | "police" | "done">(""); const [rej, setRej] = useState<D | null>(null);
  const run = async (p: string, body?: unknown, msg?: string) => { try { const r = await api<C>(`/onboarding/cases/${c.id}${p}`, { method: "POST", body }); if (msg) toast(msg); onChange(r); } catch (e: any) { toast(e.message); } };
  const view = async (d: D) => { const r = await fetch(`/api/onboarding/cases/${c.id}/docs/${d.id}/file`, { headers: { Authorization: `Bearer ${store.token}`, "X-Property-Id": String(store.prop) } }); if (r.ok) window.open(URL.createObjectURL(await r.blob()), "_blank"); };
  const m = c.missing; const complete = !m.fields.length && !m.docs.length && !m.docs_open.length; const idx = STEPS.indexOf(c.status); const link = typeof window !== "undefined" ? `${window.location.origin}/t/${c.token}` : "";
  const docMap = Object.fromEntries((c.docs ?? []).map((d) => [d.kind, d]));
  return <Modal title={`${c.unit} · ${c.name}`} onClose={onClose}><div style={{ maxHeight: "74vh", overflowY: "auto", paddingRight: 4 }}>
    <div className="row wrap" style={{ gap: 6, marginBottom: 14 }}>{STEPS.map((s, i) => <Chip key={s} tone={i < idx ? "ok" : i === idx ? "info" : "mute"}>{i + 1}. {t(`ob.step.${s}`)}</Chip>)}</div>
    {review && <div className="row wrap" style={{ marginBottom: 14 }}>
      {c.status === "review" && <Btn onClick={() => run("/verify")} disabled={!complete}>{t("ob.verify")}</Btn>}
      {["verified", "police", "done"].includes(c.status) && <a className="btn soft" href={`/app/onboarding/${c.id}/pack`}>{t("ob.pack")}</a>}
      {c.status === "verified" && <Btn onClick={() => setSub("police")}>{t("ob.police")}</Btn>}{c.status === "police" && <Btn onClick={() => setSub("done")}>{t("ob.done")}</Btn>}
      {["invited", "review"].includes(c.status) && <Btn variant="ghost" onClick={() => confirm(t("ob.cancel_confirm")) && run("/cancel")}>{t("ob.cancel")}</Btn>}</div>}
    <div className="grid g3 small" style={{ marginBottom: 12 }}>{[[t("ob.rent"), money(c.rent)], [t("ob.advance"), money(c.advance)], [t("ob.start"), fdate(c.start_date)]].map(([k, v]) => <div key={k}><span className="muted">{k}</span><br /><b style={{ fontSize: 16 }}>{v}</b></div>)}</div>
    {c.status === "invited" && c.token && <div className="card" style={{ padding: 12, marginBottom: 12 }}><div className="small muted">{t("ob.link")}</div><code style={{ wordBreak: "break-all" }}>{link}</code><div className="row" style={{ marginTop: 8 }}><Btn size="sm" variant="soft" onClick={() => { navigator.clipboard?.writeText(link); toast(t("ob.copied")); }}>{t("ob.copy")}</Btn><Btn size="sm" variant="ghost" onClick={async () => { await api(`/onboarding/cases/${c.id}/resend`, { method: "POST" }); toast(t("ob.resent")); }}>{t("ob.resend")}</Btn></div></div>}
    <h3 style={{ margin: "8px 0" }}>{t("ob.detail")}</h3>
    <div className="grid g2 small">{["father_name", "mother_name", "profession", "employer", "permanent_address", "previous_address", "emergency_name", "emergency_phone", "reference_name", "reference_phone"].map((k) => <div key={k}><span className="muted">{t(`ob.fld.${k}`)}</span><br /><b>{c.details?.[k] || "–"}</b></div>)}<div><span className="muted">{t("ob.fld.nid")}</span><br /><b>{c.nid || "–"}</b></div>
      <div><span className="muted">{t("ob.fld.family")}</span><br /><b>{(c.details?.family ?? []).map((f: any) => `${f.name} (${f.relation}, ${f.age})`).join("; ") || "–"}</b></div></div>
    <h3 style={{ margin: "16px 0 8px" }}>{t("ob.docs")}</h3>
    {DOCS.map((k) => { const d = docMap[k]; const req = k === "nid_front" || k === "nid_back" || k === "photo"; return (<div key={k} className="row between wrap" style={{ padding: "8px 0", borderTop: "1px solid var(--line)", gap: 8 }}>
      <div><b>{t(`ob.doc.${k}`)}</b> <span className="small muted">· {t(req ? "ob.doc.required" : "ob.doc.optional")}</span>{d && <div className="small muted">{d.filename} · {t("ob.doc.size", { n: Math.max(1, Math.round(d.size / 1024)) })}{d.note && ` · ${d.note}`}</div>}</div>
      <div className="row">{d ? <><Chip tone={d.status === "accepted" ? "ok" : d.status === "rejected" ? "bad" : "warn"}>{t(`ob.doc.${d.status}`)}</Chip>{review && <><Btn size="sm" variant="ghost" onClick={() => view(d)}>{t("ob.doc.view")}</Btn>{d.status !== "accepted" && c.status === "review" && <Btn size="sm" onClick={() => run(`/docs/${d.id}/review`, { status: "accepted" })}>{t("ob.doc.accept")}</Btn>}{d.status !== "rejected" && c.status === "review" && <Btn size="sm" variant="outline" onClick={() => setRej(d)}>{t("ob.doc.reject")}</Btn>}</>}</> : <Chip tone="mute">{t("ob.doc.missing")}</Chip>}</div></div>); })}
    {c.status === "review" && <p className="hint" style={{ marginTop: 10 }}>{complete ? t("ob.ready") : t("ob.missing_fields", { l: [...m.fields.map((f) => t(`ob.fld.${f}`)), ...m.docs.map((d) => t(`ob.doc.${d}`)), ...m.docs_open.map((d) => t(`ob.doc.${d}`))].join(", ") })}</p>}
    {c.police_ref && <p className="small"><b>{t("ob.police_ref")}:</b> {c.police_ref} · {fdate(c.police_on)}{c.receipt_no && <> · <b>{t("ob.receipt")}:</b> {c.receipt_no}</>}</p>}
    <h3 style={{ margin: "16px 0 8px" }}>{t("ob.timeline")}</h3>{(c.events ?? []).slice().reverse().map((e, i) => <div key={i} className="row between small" style={{ padding: "4px 0", borderTop: "1px solid var(--line)" }}><span>{t(`ob.ev.${e.key}`, { n: e.by })}{e.note && ` · ${e.note}`}</span><span className="muted">{ftime(e.at)}</span></div>)}
    <p className="hint" style={{ marginTop: 14 }}>{t("ob.person_note")}</p>
  </div>
    {sub && <Record kind={sub} onClose={() => setSub("")} onSave={(b) => { run(sub === "police" ? "/police" : "/done", b); setSub(""); }} />}
    {rej && <Reject d={rej} onClose={() => setRej(null)} onSave={(note) => { run(`/docs/${rej.id}/review`, { status: "rejected", note }); setRej(null); }} />}
  </Modal>;
}
function Record({ kind, onClose, onSave }: { kind: "police" | "done"; onClose: () => void; onSave: (b: Record<string, string>) => void }) {
  const { t } = useT(); const [ref, setRef] = useState(""); const [on, setOn] = useState(new Date().toISOString().slice(0, 10));
  return <Modal title={t(kind === "police" ? "ob.police" : "ob.done")} onClose={onClose}><Field label={t(kind === "police" ? "ob.police_ref" : "ob.receipt")}><input className="input" value={ref} onChange={(e) => setRef(e.target.value)} /></Field>
    {kind === "police" && <Field label={t("ob.police_on")}><input className="input" type="date" value={on} onChange={(e) => setOn(e.target.value)} /></Field>}<div className="row"><Btn disabled={ref.trim().length < 2} onClick={() => onSave(kind === "police" ? { reference_no: ref, submitted_on: on } : { receipt_no: ref })}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}
function Reject({ d, onClose, onSave }: { d: D; onClose: () => void; onSave: (n: string) => void }) {
  const { t } = useT(); const [n, setN] = useState("");
  return <Modal title={`${t("ob.doc.reject")} · ${t(`ob.doc.${d.kind}`)}`} onClose={onClose}><Field label={t("ob.doc.note")}><input className="input" value={n} onChange={(e) => setN(e.target.value)} /></Field><div className="row"><Btn variant="danger" onClick={() => onSave(n)}>{t("ob.doc.reject")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}
