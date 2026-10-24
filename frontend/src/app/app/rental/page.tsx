"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Btn, Card, Chip, Empty, Field, Modal, PageHead, Stat, Tabs, useToast } from "@/components/ui";
import { api, fdate, ftime, money, store } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type Flat = { unit_id: number; number: string; side: "owner" | "tenant"; enabled: boolean };
type Agr = { id: number; title: string; start_date: string; end_date: string | null; rent: number; advance: number; filename: string; days_left: number | null; expired: boolean; expiring: boolean };
type Pay = { id: number; period: string; amount: number; method: string; paid_on: string; note: string; bank_ref: string; status: string; source: string; receipt_no: string };
type Month = { period: string; due: number; received: number; outstanding: number; balance: number; overdue: boolean };
type Issue = { id: number; title: string; body: string; status: string; cost: number | null; cost_note: string; has_photo: boolean; raised_side: string; at: string };
type Fu = { id: number; text: string; due_date: string | null; ref_kind: string; ref: string; done: boolean; overdue: boolean };
type Note = { id: number; kind: string; period: string; body: string; sms_status: string; at: string; by: string };
type Data = {
  unit: { id: number; number: string }; side: "owner" | "tenant"; people: { kind: string; name: string; name_bn: string; phone: string }[];
  agreements: Agr[]; expiring: number[]; payments: Pay[]; notes: Note[]; issues: Issue[]; followups: Fu[];
  ledger: { months: Month[]; total_due: number; total_received: number; balance: number; overdue: Month[]; overdue_amount: number };
};
type TabId = "agreements" | "rent" | "issues" | "follow";
const paisa = (v: string) => Math.round(parseFloat(v || "0") * 100);
const authHeaders = () => ({ Authorization: `Bearer ${store.token}`, "X-Property-Id": String(store.prop) });

async function form<T = any>(path: string, fd: FormData): Promise<T> {
  const r = await fetch(`/api${path}`, { method: "POST", headers: authHeaders(), body: fd });
  if (!r.ok) { let m = r.statusText; try { const j = await r.json(); m = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch {} throw new Error(m); }
  return r.json();
}
async function openFile(path: string) { const r = await fetch(`/api${path}`, { headers: authHeaders() }); if (r.ok) window.open(URL.createObjectURL(await r.blob()), "_blank"); }

export default function Rental() {
  const { t } = useT(); const { prop } = useAuth(); const toast = useToast();
  const [flats, setFlats] = useState<Flat[] | null>(null); const [uid, setUid] = useState(0);
  const [d, setD] = useState<Data | null>(null); const [err, setErr] = useState(""); const [tab, setTab] = useState<TabId>("rent");
  const loadFlats = useCallback(() => api<Flat[]>("/rental/flats").then((f) => { setFlats(f); setUid((u) => (f.some((x) => x.unit_id === u) ? u : f[0]?.unit_id ?? 0)); }).catch((e) => { setErr(e.message); setFlats([]); }), []);
  useEffect(() => { loadFlats(); }, [loadFlats, prop?.id]);
  const flat = flats?.find((f) => f.unit_id === uid);
  const load = useCallback(() => { if (flat?.enabled) api<Data>(`/rental/units/${flat.unit_id}`).then((x) => { setD(x); setErr(""); }).catch((e) => setErr(e.message)); else setD(null); }, [flat?.unit_id, flat?.enabled]);
  useEffect(() => { load(); }, [load]);
  const run = async (p: Promise<any>, ok?: string) => { try { await p; if (ok) toast.show(ok); await load(); } catch (e: any) { toast.show(e.message); } };
  const setSwitch = async (on: boolean) => { if (!on && !confirm(t("rent.turn_off_confirm"))) return; try { await api(`/rental/units/${uid}/switch`, { method: "PUT", body: { enabled: on } }); toast.show(t("rent.switched")); await loadFlats(); } catch (e: any) { toast.show(e.message); } };

  if (!flats) return <p className="muted">{t("common.loading")}</p>;
  if (!flats.length) return (<><PageHead title={t("rent.title")} sub={t("rent.sub")} /><Card><p className="muted">{err || t("rent.off_tenant")}</p></Card></>);
  const owner = flat?.side === "owner";
  return (<>
    <PageHead title={t("rent.title")} sub={t("rent.sub")} />
    {flats.length > 1 && <div style={{ marginBottom: 14 }}><Field label={t("rent.flat")}><select className="input" value={uid} onChange={(e) => { setUid(Number(e.target.value)); setD(null); }}>{flats.map((f) => <option key={f.unit_id} value={f.unit_id}>{f.number}</option>)}</select></Field></div>}
    <p className="small muted" style={{ marginBottom: 14 }}>🔒 {t("rent.private")}</p>
    {owner && <Card style={{ marginBottom: 16 }}><div className="row between wrap"><div><h3 style={{ margin: 0 }}>{t("rent.switch")} · {flat!.number}</h3><p className="small muted" style={{ margin: "4px 0 0" }}>{t("rent.switch_hint")}</p></div>
      <div className="row"><Chip tone={flat!.enabled ? "ok" : "mute"}>{t(flat!.enabled ? "rent.switch_on" : "rent.switch_off")}</Chip><Btn variant={flat!.enabled ? "outline" : "primary"} onClick={() => setSwitch(!flat!.enabled)}>{t(flat!.enabled ? "rent.turn_off" : "rent.turn_on")}</Btn></div></div></Card>}
    {err && !d && <p className="error">{err}</p>}
    {flat?.enabled && !d && !err && <p className="muted">{t("common.loading")}</p>}
    {d && (<>
      {d.expiring.length > 0 && <Card style={{ marginBottom: 14, borderColor: "var(--warn)" }}><b>⚠ {t("rent.ag.renew_banner")}</b></Card>}
      <div className="grid g3" style={{ marginBottom: 16 }}>
        <Stat label={t("rent.due")} value={money(d.ledger.total_due)} /><Stat label={t("rent.received")} value={money(d.ledger.total_received)} />
        <Stat label={t("rent.balance")} value={money(d.ledger.balance)} note={d.ledger.overdue.length ? <Chip tone="bad">{t("rent.overdue")}: {money(d.ledger.overdue_amount)}</Chip> : undefined} />
      </div>
      <div style={{ marginBottom: 16 }}><Tabs value={tab} onChange={setTab} items={[{ id: "rent", label: t("rent.tab.rent") }, { id: "agreements", label: t("rent.tab.agreements") }, { id: "issues", label: `${t("rent.tab.issues")}${d.issues.filter((i) => i.status === "open").length ? ` · ${d.issues.filter((i) => i.status === "open").length}` : ""}` }, { id: "follow", label: t("rent.tab.follow") }]} /></div>
      {tab === "rent" && <RentTab d={d} run={run} toast={toast.show} />}
      {tab === "agreements" && <AgreementsTab d={d} run={run} />}
      {tab === "issues" && <IssuesTab d={d} run={run} />}
      {tab === "follow" && <FollowTab d={d} run={run} />}
    </>)}
    {toast.node}
  </>);
}

type Run = (p: Promise<any>, ok?: string) => Promise<void>;

function RentTab({ d, run, toast }: { d: Data; run: Run; toast: (m: string) => void }) {
  const { t } = useT(); const owner = d.side === "owner"; const uid = d.unit.id;
  const [open, setOpen] = useState(false); const [noteOpen, setNoteOpen] = useState(false);
  const stChip = (s: string) => <Chip tone={s === "confirmed" ? "ok" : s === "pending" ? "warn" : "bad"}>{t(`rent.st.${s}`)}</Chip>;
  const remind = async (period: string) => { try { const r = await api(`/rental/units/${uid}/remind`, { method: "POST", body: { period } }); toast(r.status === "sent" ? t("rent.remind_sent") : t("rent.remind_failed", { e: r.error })); await run(Promise.resolve()); } catch (e: any) { toast(e.message); } };
  const receipt = async (p: Pay) => { await run(api(`/rental/payments/${p.id}/receipt`, { method: "POST" })); window.location.href = `/app/rental/receipt/${p.id}`; };
  return (<div className="stack">
    <div className="row wrap"><Btn onClick={() => setOpen(true)}>{owner ? t("rent.record") : t("rent.i_paid")}</Btn>{owner && <Btn variant="soft" onClick={() => setNoteOpen(true)}>{t("rent.add_note")}</Btn>}</div>
    <Card><h3 style={{ marginTop: 0 }}>{t("rent.ledger")}</h3>
      <div className="table-wrap"><table className="t"><thead><tr><th>{t("rent.month")}</th><th className="num">{t("rent.due")}</th><th className="num">{t("rent.received")}</th><th className="num">{t("rent.balance")}</th><th /></tr></thead>
        <tbody>{[...d.ledger.months].reverse().map((m) => <tr key={m.period}><td>{m.period}</td><td className="num">{money(m.due)}</td><td className="num">{money(m.received)}</td><td className="num">{money(m.balance)}</td><td>{m.overdue && <Chip tone="bad">{t("rent.overdue")}</Chip>}</td></tr>)}
          {!d.ledger.months.length && <tr><td colSpan={5}><Empty /></td></tr>}</tbody></table></div></Card>
    {owner && <Card><h3 style={{ marginTop: 0 }}>{t("rent.follow_list")}</h3>
      {d.ledger.overdue.length === 0 ? <p className="muted">{t("rent.none_overdue")}</p> : d.ledger.overdue.map((m) => (
        <div key={m.period} className="row between wrap" style={{ padding: "8px 0", borderTop: "1px solid var(--line)" }}><span><b>{m.period}</b> · {money(m.outstanding)}</span>
          <Btn size="sm" variant="soft" disabled={!d.people.some((p) => p.kind === "tenant")} onClick={() => remind(m.period)}>{t("rent.remind")}</Btn></div>))}
      <p className="small muted">{t("rent.remind_cost")}</p>
      {d.notes.length > 0 && <><h3 style={{ margin: "14px 0 4px" }}>{t("rent.history_notes")}</h3>{d.notes.map((n) => (
        <div key={n.id} className="small" style={{ padding: "6px 0", borderTop: "1px solid var(--line)" }}><Chip tone={n.kind === "reminder" ? "info" : "mute"}>{t(n.kind === "reminder" ? "rent.reminder" : "rent.noteword")}</Chip> {n.period && <b>{n.period} </b>}
          {n.kind === "note" && n.body} {n.sms_status && <span className="muted">· {t(`rent.sms.${n.sms_status}`)}</span>} <span className="muted">· {ftime(n.at)}</span></div>))}</>}
    </Card>}
    <Card><h3 style={{ marginTop: 0 }}>{t("rent.history")}</h3>
      {d.payments.length === 0 && <p className="muted">{t("rent.none_pay")}</p>}
      {d.payments.map((p) => (<div key={p.id} className="row between wrap" style={{ padding: "10px 0", borderTop: "1px solid var(--line)" }}>
        <div><b>{p.period} · {money(p.amount)}</b> {stChip(p.status)}<div className="small muted">{t(`rent.m.${p.method}`)} · {fdate(p.paid_on)}{p.bank_ref && ` · ${p.bank_ref}`}{p.note && ` · ${p.note}`}{p.receipt_no && ` · ${p.receipt_no}`}</div></div>
        <div className="row wrap">
          {owner && p.status === "pending" && <><Btn size="sm" onClick={() => run(api(`/rental/payments/${p.id}/confirm`, { method: "POST" }))}>{t("rent.confirm")}</Btn><Btn size="sm" variant="outline" onClick={() => run(api(`/rental/payments/${p.id}/reject`, { method: "POST" }))}>{t("rent.reject")}</Btn></>}
          {p.status === "confirmed" && p.receipt_no && <Link href={`/app/rental/receipt/${p.id}`} className="btn btn-soft btn-sm">{t("rent.view_receipt")}</Link>}
          {owner && p.status === "confirmed" && !p.receipt_no && <Btn size="sm" variant="soft" onClick={() => receipt(p)}>{t("rent.make_receipt")}</Btn>}
          {owner && !p.receipt_no && <Btn size="sm" variant="ghost" onClick={() => confirm(t("rent.delete_confirm")) && run(api(`/rental/payments/${p.id}`, { method: "DELETE" }))}>{t("rent.delete")}</Btn>}
        </div></div>))}</Card>
    {open && <PayModal d={d} onClose={() => setOpen(false)} onDone={() => { setOpen(false); run(Promise.resolve(), owner ? t("rent.recorded") : t("rent.claim_sent")); }} />}
    {noteOpen && <NoteModal uid={uid} onClose={() => setNoteOpen(false)} onDone={() => { setNoteOpen(false); run(Promise.resolve(), t("rent.recorded")); }} />}
  </div>);
}

function PayModal({ d, onClose, onDone }: { d: Data; onClose: () => void; onDone: () => void }) {
  const { t } = useT();
  const first = d.ledger.overdue[0] ?? d.ledger.months.find((m) => m.outstanding > 0);
  const [f, setF] = useState({ period: first?.period ?? new Date().toISOString().slice(0, 7), amount: first ? String(first.outstanding / 100) : "", method: "cash", paid_on: new Date().toISOString().slice(0, 10), bank_ref: "", note: "" });
  const [err, setErr] = useState("");
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const save = async () => { try { await api(`/rental/units/${d.unit.id}/payments`, { method: "POST", body: { ...f, amount: paisa(f.amount) } }); onDone(); } catch (e: any) { setErr(e.message); } };
  return (<Modal title={d.side === "owner" ? t("rent.record") : t("rent.i_paid")} onClose={onClose}>
    <div className="grid g2"><Field label={t("rent.month")}><input className="input" type="month" value={f.period} onChange={set("period")} /></Field><Field label={t("rent.amount")}><input className="input" inputMode="decimal" value={f.amount} onChange={set("amount")} /></Field>
      <Field label={t("rent.method")}><select className="input" value={f.method} onChange={set("method")}><option value="cash">{t("rent.m.cash")}</option><option value="bank">{t("rent.m.bank")}</option></select></Field><Field label={t("rent.date")}><input className="input" type="date" value={f.paid_on} onChange={set("paid_on")} /></Field></div>
    {f.method === "bank" && <Field label={t("rent.bank_ref")}><input className="input" maxLength={60} value={f.bank_ref} onChange={set("bank_ref")} /></Field>}
    <Field label={t("rent.note")}><input className="input" maxLength={300} value={f.note} onChange={set("note")} /></Field>
    {err && <p className="error">{err}</p>}<div className="row"><Btn onClick={save} disabled={!f.amount}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>);
}

function NoteModal({ uid, onClose, onDone }: { uid: number; onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [body, setBody] = useState(""); const [err, setErr] = useState("");
  const save = async () => { try { await api(`/rental/units/${uid}/notes`, { method: "POST", body: { body } }); onDone(); } catch (e: any) { setErr(e.message); } };
  return (<Modal title={t("rent.add_note")} onClose={onClose}><Field label={t("rent.note")}><textarea className="input" maxLength={400} placeholder={t("rent.note_ph")} value={body} onChange={(e) => setBody(e.target.value)} /></Field>
    {err && <p className="error">{err}</p>}<div className="row"><Btn onClick={save} disabled={!body.trim()}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>);
}

function AgreementsTab({ d, run }: { d: Data; run: Run }) {
  const { t } = useT(); const owner = d.side === "owner"; const [open, setOpen] = useState(false);
  return (<div className="stack">
    {owner && <div><Btn onClick={() => setOpen(true)}>{t("rent.ag.add")}</Btn></div>}
    {d.agreements.length === 0 && <Card><p className="muted">{t("rent.ag.none")}</p></Card>}
    {d.agreements.map((a) => (<Card key={a.id}><div className="row between wrap"><div><h3 style={{ margin: 0 }}>{a.title}</h3>
      <p className="small muted" style={{ margin: "4px 0" }}>{fdate(a.start_date)} → {a.end_date ? fdate(a.end_date) : t("rent.ag.open_end")} · {t("rent.ag.rent")}: {money(a.rent)} · {t("rent.ag.advance")}: {money(a.advance)}</p></div>
      {a.expired ? <Chip tone="bad">{t("rent.ag.expired")}</Chip> : a.expiring ? <Chip tone="warn">{t("rent.ag.expiring", { n: a.days_left ?? 0 })}</Chip> : a.days_left !== null ? <Chip tone="ok">{t("rent.ag.ok", { n: a.days_left })}</Chip> : null}</div>
      <div className="row wrap" style={{ marginTop: 10 }}><Btn size="sm" variant="soft" onClick={() => openFile(`/rental/agreements/${a.id}/file`)}>{t("rent.ag.open")} · {a.filename}</Btn>
        {owner && <Btn size="sm" variant="ghost" onClick={() => confirm(t("rent.ag.delete_confirm")) && run(api(`/rental/agreements/${a.id}`, { method: "DELETE" }))}>{t("rent.ag.delete")}</Btn>}</div></Card>))}
    {open && <AgreementModal uid={d.unit.id} onClose={() => setOpen(false)} onDone={() => { setOpen(false); run(Promise.resolve(), t("rent.ag.saved")); }} />}
  </div>);
}

function AgreementModal({ uid, onClose, onDone }: { uid: number; onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [f, setF] = useState({ title: "", start_date: "", end_date: "", rent: "", advance: "" }); const [file, setFile] = useState<File | null>(null); const [err, setErr] = useState("");
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    if (file && file.size > 3 * 1024 * 1024) return setErr("3 MB");
    const fd = new FormData(); fd.append("title", f.title); fd.append("start_date", f.start_date); if (f.end_date) fd.append("end_date", f.end_date); fd.append("rent", String(paisa(f.rent))); fd.append("advance", String(paisa(f.advance))); fd.append("file", file!);
    try { await form(`/rental/units/${uid}/agreements`, fd); onDone(); } catch (e: any) { setErr(e.message); }
  };
  return (<Modal title={t("rent.ag.add")} onClose={onClose}>
    <Field label={t("rent.ag.title")}><input className="input" maxLength={160} value={f.title} onChange={set("title")} /></Field>
    <div className="grid g2"><Field label={t("rent.ag.start")}><input className="input" type="date" value={f.start_date} onChange={set("start_date")} /></Field><Field label={t("rent.ag.end")}><input className="input" type="date" value={f.end_date} onChange={set("end_date")} /></Field>
      <Field label={t("rent.ag.rent")}><input className="input" inputMode="decimal" value={f.rent} onChange={set("rent")} /></Field><Field label={t("rent.ag.advance")}><input className="input" inputMode="decimal" value={f.advance} onChange={set("advance")} /></Field></div>
    <Field label={t("rent.ag.file")}><input className="input" type="file" accept="application/pdf,image/jpeg,image/png" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
    {err && <p className="error">{err}</p>}<div className="row"><Btn onClick={save} disabled={!f.title || !f.start_date || !file}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>);
}

function IssuesTab({ d, run }: { d: Data; run: Run }) {
  const { t } = useT(); const [open, setOpen] = useState(false); const [sel, setSel] = useState<number | null>(null);
  const tone = (s: string) => (s === "open" ? "bad" : s === "in_progress" ? "warn" : s === "fixed" ? "ok" : "mute") as any;
  return (<div className="stack">
    <div><Btn onClick={() => setOpen(true)}>{t("rent.is.add")}</Btn></div>
    {d.issues.length === 0 && <Card><p className="muted">{t("rent.is.none")}</p></Card>}
    {d.issues.map((i) => (<Card key={i.id}><div className="row between wrap"><div><h3 style={{ margin: 0 }}>{i.title}</h3><p className="small muted" style={{ margin: "4px 0" }}>{t("rent.is.by", { who: t(`rent.side.${i.raised_side}`) })} · {fdate(i.at)}{i.cost !== null && ` · ${t("rent.is.cost")}: ${money(i.cost)}`}</p></div>
      <div className="row"><Chip tone={tone(i.status)}>{t(`rent.is.${i.status}`)}</Chip><Btn size="sm" variant="soft" onClick={() => setSel(i.id)}>{t("common.view")}</Btn></div></div>{i.body && <p>{i.body}</p>}</Card>))}
    {open && <IssueModal uid={d.unit.id} onClose={() => setOpen(false)} onDone={() => { setOpen(false); run(Promise.resolve(), t("rent.is.raised")); }} />}
    {sel && <IssueDetail id={sel} owner={d.side === "owner"} onClose={() => { setSel(null); run(Promise.resolve()); }} />}
  </div>);
}

function IssueModal({ uid, onClose, onDone }: { uid: number; onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [title, setTitle] = useState(""); const [body, setBody] = useState(""); const [photo, setPhoto] = useState<File | null>(null); const [err, setErr] = useState("");
  const save = async () => { const fd = new FormData(); fd.append("title", title); fd.append("body", body); if (photo) fd.append("photo", photo); try { await form(`/rental/units/${uid}/issues`, fd); onDone(); } catch (e: any) { setErr(e.message); } };
  return (<Modal title={t("rent.is.add")} onClose={onClose}><Field label={t("rent.is.title")}><input className="input" maxLength={160} value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
    <Field label={t("rent.is.body")}><textarea className="input" value={body} onChange={(e) => setBody(e.target.value)} /></Field>
    <Field label={t("rent.is.photo")}><input className="input" type="file" accept="image/jpeg,image/png" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} /></Field>
    {err && <p className="error">{err}</p>}<div className="row"><Btn onClick={save} disabled={!title.trim()}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>);
}

function IssueDetail({ id, owner, onClose }: { id: number; owner: boolean; onClose: () => void }) {
  const { t } = useT();
  const [i, setI] = useState<(Issue & { comments: { id: number; side: string; body: string; by: string; at: string }[] }) | null>(null);
  const [c, setC] = useState(""); const [cost, setCost] = useState(""); const [note, setNote] = useState(""); const [err, setErr] = useState("");
  const load = useCallback(() => api(`/rental/issues/${id}`).then((x) => { setI(x); setCost(x.cost !== null ? String(x.cost / 100) : ""); setNote(x.cost_note); }), [id]);
  useEffect(() => { load(); }, [load]);
  const patch = async (body: object) => { try { await api(`/rental/issues/${id}`, { method: "PATCH", body }); await load(); } catch (e: any) { setErr(e.message); } };
  const send = async () => { try { await api(`/rental/issues/${id}/comments`, { method: "POST", body: { body: c } }); setC(""); await load(); } catch (e: any) { setErr(e.message); } };
  if (!i) return null;
  return (<Modal title={i.title} onClose={onClose}>
    {i.body && <p>{i.body}</p>}{i.has_photo && <p><Btn size="sm" variant="soft" onClick={() => openFile(`/rental/issues/${id}/photo`)}>{t("rent.is.photo_view")}</Btn></p>}
    <Field label={t("rent.is.status")}><select className="input" value={i.status} onChange={(e) => patch({ status: e.target.value })}>{["open", "in_progress", "fixed", "closed"].map((s) => <option key={s} value={s}>{t(`rent.is.${s}`)}</option>)}</select></Field>
    {owner && <div className="grid g2"><Field label={t("rent.is.cost")}><input className="input" inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} /></Field><Field label={t("rent.is.cost_note")}><input className="input" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      <div><Btn size="sm" variant="soft" onClick={() => patch({ cost: paisa(cost), cost_note: note })}>{t("rent.is.save")}</Btn></div></div>}
    <h3>{t("rent.is.comments")}</h3>
    {i.comments.map((m) => <div key={m.id} className="small" style={{ padding: "6px 0", borderTop: "1px solid var(--line)" }}><b>{t(`rent.side.${m.side}`)}</b> <span className="muted">· {ftime(m.at)}</span><div>{m.body}</div></div>)}
    <div className="row" style={{ marginTop: 10 }}><input className="input" maxLength={1000} placeholder={t("rent.is.comment")} value={c} onChange={(e) => setC(e.target.value)} /><Btn onClick={send} disabled={!c.trim()}>{t("rent.is.send")}</Btn></div>
    {err && <p className="error">{err}</p>}</Modal>);
}

function FollowTab({ d, run }: { d: Data; run: Run }) {
  const { t } = useT(); const [open, setOpen] = useState(false);
  return (<div className="stack">
    <div><Btn onClick={() => setOpen(true)}>{t("rent.fu.add")}</Btn></div>
    <Card>{d.followups.length === 0 && <p className="muted">{t("rent.fu.none")}</p>}
      {d.followups.map((f) => (<div key={f.id} className="row between wrap" style={{ padding: "10px 0", borderTop: "1px solid var(--line)" }}>
        <label className="row" style={{ gap: 10 }}><input type="checkbox" checked={f.done} onChange={(e) => run(api(`/rental/followups/${f.id}`, { method: "PATCH", body: { done: e.target.checked } }))} />
          <span style={{ textDecoration: f.done ? "line-through" : undefined }}>{f.text}<span className="small muted">{f.due_date && ` · ${fdate(f.due_date)}`}{f.ref_kind && ` · ${t(`rent.fu.${f.ref_kind}`)} ${f.ref}`}</span></span></label>
        <div className="row">{f.overdue && <Chip tone="bad">{t("rent.fu.late")}</Chip>}{f.done && <Chip tone="ok">{t("rent.fu.done")}</Chip>}<Btn size="sm" variant="ghost" onClick={() => run(api(`/rental/followups/${f.id}`, { method: "DELETE" }))}>{t("rent.delete")}</Btn></div></div>))}</Card>
    {open && <FollowModal uid={d.unit.id} onClose={() => setOpen(false)} onDone={() => { setOpen(false); run(Promise.resolve(), t("rent.recorded")); }} />}
  </div>);
}

function FollowModal({ uid, onClose, onDone }: { uid: number; onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [f, setF] = useState({ text: "", due_date: "", ref_kind: "", ref: "" }); const [err, setErr] = useState("");
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const save = async () => { try { await api(`/rental/units/${uid}/followups`, { method: "POST", body: { ...f, due_date: f.due_date || null } }); onDone(); } catch (e: any) { setErr(e.message); } };
  return (<Modal title={t("rent.fu.add")} onClose={onClose}><Field label={t("rent.fu.text")}><input className="input" maxLength={300} value={f.text} onChange={set("text")} /></Field>
    <div className="grid g2"><Field label={t("rent.fu.due")}><input className="input" type="date" value={f.due_date} onChange={set("due_date")} /></Field>
      <Field label={t("rent.fu.tie")}><select className="input" value={f.ref_kind} onChange={set("ref_kind")}><option value="">{t("rent.fu.none_tie")}</option><option value="rent">{t("rent.fu.rent")}</option><option value="issue">{t("rent.fu.issue")}</option></select></Field></div>
    {f.ref_kind && <Field label={t("rent.fu.ref")}><input className="input" maxLength={16} value={f.ref} onChange={set("ref")} /></Field>}
    {err && <p className="error">{err}</p>}<div className="row"><Btn onClick={save} disabled={!f.text.trim()}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>);
}
