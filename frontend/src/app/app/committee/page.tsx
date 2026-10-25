"use client";
import { useCallback, useEffect, useState } from "react";
import { Btn, Card, Chip, Empty, Field, Modal, PageHead, Tabs, useToast } from "@/components/ui";
import { Pager } from "@/components/pager";
import { api, fdate } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

const ROLES = ["president", "secretary", "treasurer", "member"];
const SIZE = 10;
type Paged<T> = { items: T[]; total: number; page: number; size: number };
type M = { id: number; name: string; name_bn: string; role: string; start_date: string; end_date: string; note: string; current: boolean; expired: boolean; upcoming: boolean; expiring_soon: boolean; days_left: number };
type Mt = { id: number; title: string; held_on: string; place: string; status: string; present: number; invited: number; decisions_n: number; agenda?: string; attendance?: { member_id: number; name: string; name_bn: string; role: string; present: boolean }[]; minutes?: string; decisions?: string[] };
type P = { id: number; title: string; text: string; status: string; result: string; tally: { approve: number; reject: number; eligible: number }; voted: number; my_vote: string | null; can_vote: boolean; created_by: string; created_at: string; votes: { name: string; choice: string }[] };

export default function Committee() {
  const { t } = useT(); const { prop, has } = useAuth(); const toast = useToast();
  const edit = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY");
  const [tab, setTab] = useState<"members" | "history" | "meetings" | "votes">("members");
  return (<>
    <PageHead helpKey="committee-meetings" title={t("cm.title")} sub={t("cm.sub")} />
    <div style={{ marginBottom: 14 }}><Tabs value={tab} onChange={setTab} items={[{ id: "members", label: t("cm.tab.members") }, { id: "history", label: t("cm.tab.history") }, { id: "meetings", label: t("cm.tab.meetings") }, { id: "votes", label: t("cm.tab.votes") }]} /></div>
    {(tab === "members" || tab === "history") && <Members key={tab + prop?.id} scope={tab === "members" ? "current" : "history"} edit={edit} toast={toast.show} />}
    {tab === "meetings" && <Meetings key={prop?.id} edit={edit} toast={toast.show} />}
    {tab === "votes" && <Votes key={prop?.id} edit={edit} toast={toast.show} />}
    {toast.node}
  </>);
}

function Members({ scope, edit, toast }: { scope: "current" | "history"; edit: boolean; toast: (m: string) => void }) {
  const { t, pick } = useT(); const [d, setD] = useState<(Paged<M> & { expiring: number }) | null>(null); const [page, setPage] = useState(1); const [q, setQ] = useState(""); const [form, setForm] = useState<{ m?: M } | null>(null);
  const load = useCallback(() => api<Paged<M> & { expiring: number }>(`/committee/members?${new URLSearchParams({ scope, page: String(page), size: String(SIZE), q })}`).then(setD), [scope, page, q]);
  useEffect(() => { load(); }, [load]);
  const state = (m: M) => m.expired ? <Chip tone="mute">{t("cm.expired")}</Chip> : m.upcoming ? <Chip tone="info">{t("cm.upcoming")}</Chip> : m.expiring_soon ? <Chip tone="warn">{t("cm.expiring", { n: m.days_left })}</Chip> : <Chip tone="ok">{t("cm.serving")}</Chip>;
  return <>
    {scope === "current" && d && d.expiring > 0 && <Card style={{ borderColor: "var(--warn)", marginBottom: 14 }}><b>{t("cm.expiring_n", { n: d.expiring })}</b></Card>}
    <div className="toolbar"><input className="input" placeholder={t("cm.search")} aria-label={t("cm.search")} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />{edit && scope === "current" && <Btn onClick={() => setForm({})}>{t("cm.add")}</Btn>}</div>
    {!d ? <p className="muted">{t("common.loading")}</p> : d.items.length === 0 ? <Card><Empty>{t("cm.empty")}</Empty></Card> :
      <div className="table-wrap"><table className="t"><thead><tr><th>{t("cm.col.name")}</th><th>{t("cm.col.role")}</th><th>{t("cm.col.tenure")}</th><th>{t("cm.col.status")}</th>{edit && <th />}</tr></thead>
        <tbody>{d.items.map((m) => (<tr key={m.id}><td><b>{pick(m.name, m.name_bn)}</b>{m.note && <div className="small muted">{m.note}</div>}</td><td>{t(`cm.role.${m.role}`)}</td><td>{t("cm.tenure", { a: fdate(m.start_date), b: fdate(m.end_date) })}</td><td>{state(m)}</td>
          {edit && <td><Btn size="sm" variant="ghost" onClick={() => setForm({ m })}>{t("cm.extend")}</Btn></td>}</tr>))}</tbody></table></div>}
    {d && <Pager page={page} size={SIZE} total={d.total} onPage={setPage} />}
    {form && <MemberForm m={form.m} onClose={() => setForm(null)} onDone={() => { setForm(null); toast(t("rq.saved")); load(); }} />}
  </>;
}

function MemberForm({ m, onClose, onDone }: { m?: M; onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [f, setF] = useState({ name: m?.name ?? "", name_bn: m?.name_bn ?? "", role: m?.role ?? "member", start_date: m?.start_date ?? "", end_date: m?.end_date ?? "", note: m?.note ?? "" }); const [err, setErr] = useState("");
  const go = async () => { try { if (m) await api(`/committee/members/${m.id}`, { method: "PUT", body: { end_date: f.end_date, note: f.note } }); else await api("/committee/members", { body: f }); onDone(); } catch (e: any) { setErr(e.message); } };
  return <Modal title={m ? t("cm.extend") : t("cm.add")} onClose={onClose}>
    {!m && <><Field label={t("cm.f.name")}><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
      <Field label={t("cm.f.name_bn")}><input className="input" value={f.name_bn} onChange={(e) => setF({ ...f, name_bn: e.target.value })} /></Field>
      <Field label={t("cm.f.role")}><select className="input" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{ROLES.map((r) => <option key={r} value={r}>{t(`cm.role.${r}`)}</option>)}</select></Field>
      <Field label={t("cm.f.start")}><input className="input" type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></Field></>}
    <Field label={t("cm.f.end")}><input className="input" type="date" value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} /></Field>
    <Field label={t("cm.f.note")}><input className="input" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
    {err && <p className="error" role="alert">{err}</p>}
    <div className="row"><Btn onClick={go} disabled={!f.end_date || (!m && (f.name.trim().length < 2 || !f.start_date))}>{t("rq.sla.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}

function Meetings({ edit, toast }: { edit: boolean; toast: (m: string) => void }) {
  const { t } = useT(); const [d, setD] = useState<Paged<Mt> | null>(null); const [page, setPage] = useState(1); const [q, setQ] = useState(""); const [form, setForm] = useState(false); const [open, setOpen] = useState<number | null>(null);
  const load = useCallback(() => api<Paged<Mt>>(`/committee/meetings?${new URLSearchParams({ page: String(page), size: String(SIZE), q })}`).then(setD), [page, q]);
  useEffect(() => { load(); }, [load]);
  const tone = (s: string) => (s === "held" ? "ok" : s === "cancelled" ? "mute" : "info") as "ok" | "mute" | "info";
  return <>
    <div className="toolbar"><input className="input" placeholder={t("mt.search")} aria-label={t("mt.search")} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />{edit && <Btn onClick={() => setForm(true)}>{t("mt.new")}</Btn>}</div>
    {!d ? <p className="muted">{t("common.loading")}</p> : d.items.length === 0 ? <Card><Empty>{t("mt.empty")}</Empty></Card> :
      <div className="stack">{d.items.map((m) => (<Card key={m.id} style={{ cursor: "pointer" }}><div className="row between wrap" style={{ gap: 12 }} onClick={() => setOpen(m.id)}>
        <div><div style={{ marginBottom: 6 }}><Chip tone={tone(m.status)}>{t(`mt.st.${m.status}`)}</Chip></div><h3 style={{ margin: 0 }}>{m.title}</h3><span className="small muted">{fdate(m.held_on)}{m.place ? ` · ${m.place}` : ""}</span></div>
        {m.status === "held" && <div className="small muted" style={{ textAlign: "right" }}>{t("mt.attended", { p: m.present, n: m.invited })}<br />{t("mt.decisions_n", { n: m.decisions_n })}</div>}</div></Card>))}</div>}
    {d && <Pager page={page} size={SIZE} total={d.total} onPage={setPage} />}
    {form && <MeetingForm onClose={() => setForm(false)} onDone={() => { setForm(false); toast(t("rq.saved")); load(); }} />}
    {open && <MeetingModal id={open} edit={edit} onClose={() => setOpen(null)} onDone={load} />}
  </>;
}

function MeetingForm({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [f, setF] = useState({ title: "", held_on: "", place: "", agenda: "" }); const [err, setErr] = useState("");
  return <Modal title={t("mt.new")} onClose={onClose}>
    <Field label={t("mt.f.title")}><input className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
    <div className="grid g2"><Field label={t("mt.f.date")}><input className="input" type="date" value={f.held_on} onChange={(e) => setF({ ...f, held_on: e.target.value })} /></Field>
      <Field label={t("mt.f.place")}><input className="input" value={f.place} onChange={(e) => setF({ ...f, place: e.target.value })} /></Field></div>
    <Field label={t("mt.f.agenda")}><textarea className="input" rows={5} value={f.agenda} onChange={(e) => setF({ ...f, agenda: e.target.value })} /></Field>
    {err && <p className="error" role="alert">{err}</p>}
    <div className="row"><Btn disabled={f.title.trim().length < 3 || !f.held_on} onClick={async () => { try { await api("/committee/meetings", { body: f }); onDone(); } catch (e: any) { setErr(e.message); } }}>{t("mt.new")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}

function MeetingModal({ id, edit, onClose, onDone }: { id: number; edit: boolean; onClose: () => void; onDone: () => void }) {
  const { t, pick } = useT(); const [m, setM] = useState<Mt | null>(null); const [present, setPresent] = useState<number[]>([]); const [minutes, setMinutes] = useState(""); const [decisions, setDecisions] = useState<string[]>([]); const [err, setErr] = useState("");
  useEffect(() => { api<Mt>(`/committee/meetings/${id}`).then((x) => { setM(x); setPresent((x.attendance ?? []).filter((a) => a.present).map((a) => a.member_id)); setMinutes(x.minutes ?? ""); setDecisions(x.decisions?.length ? x.decisions : [""]); }); }, [id]);
  if (!m) return null;
  const editable = edit && m.status !== "cancelled" && new Date(m.held_on) <= new Date();
  const save = async () => { try { setM(await api<Mt>(`/committee/meetings/${id}/minutes`, { body: { present, minutes, decisions } })); onDone(); } catch (e: any) { setErr(e.message); } };
  return <Modal title={m.title} onClose={onClose}>
    <p className="small muted">{fdate(m.held_on)}{m.place ? ` · ${m.place}` : ""} · <Chip tone={m.status === "held" ? "ok" : m.status === "cancelled" ? "mute" : "info"}>{t(`mt.st.${m.status}`)}</Chip></p>
    {m.agenda && <><h3 style={{ marginBottom: 4 }}>{t("mt.agenda")}</h3><p style={{ whiteSpace: "pre-wrap", marginTop: 0 }}>{m.agenda}</p></>}
    <h3 style={{ marginBottom: 4 }}>{t("mt.attendance")}</h3>
    <div className="stack" style={{ marginBottom: 12 }}>{(m.attendance ?? []).map((a) => (<label key={a.member_id} className="row"><input type="checkbox" disabled={!editable} checked={present.includes(a.member_id)} onChange={(e) => setPresent(e.target.checked ? [...present, a.member_id] : present.filter((x) => x !== a.member_id))} /> {pick(a.name, a.name_bn)} <span className="small muted">· {t(`cm.role.${a.role}`)}</span>
      {!editable && <Chip tone={a.present ? "ok" : "mute"}>{t(a.present ? "mt.present" : "mt.absent")}</Chip>}</label>))}</div>
    <h3 style={{ marginBottom: 4 }}>{t("mt.minutes")}</h3>
    {editable ? <textarea className="input" rows={5} value={minutes} onChange={(e) => setMinutes(e.target.value)} /> : <p style={{ whiteSpace: "pre-wrap", marginTop: 0 }}>{m.minutes || t("mt.none_yet")}</p>}
    <h3 style={{ marginBottom: 4 }}>{t("mt.decisions")}</h3>
    {editable ? <>{decisions.map((d, i) => <input key={i} className="input" style={{ marginBottom: 6 }} value={d} onChange={(e) => setDecisions(decisions.map((x, j) => (j === i ? e.target.value : x)))} />)}<Btn size="sm" variant="ghost" onClick={() => setDecisions([...decisions, ""])}>{t("mt.add_decision")}</Btn></>
      : <ol style={{ marginTop: 0 }}>{(m.decisions ?? []).map((d, i) => <li key={i}>{d}</li>)}</ol>}
    {err && <p className="error" role="alert">{err}</p>}
    <div className="row" style={{ marginTop: 12 }}>{editable && <Btn onClick={save}>{t("mt.save_minutes")}</Btn>}
      {edit && m.status === "scheduled" && <Btn variant="danger" onClick={async () => { setM(await api<Mt>(`/committee/meetings/${id}/cancel`, { method: "POST" })); onDone(); }}>{t("mt.cancel")}</Btn>}</div></Modal>;
}

function Votes({ edit, toast }: { edit: boolean; toast: (m: string) => void }) {
  const { t } = useT(); const { has } = useAuth(); const [d, setD] = useState<Paged<P> | null>(null); const [page, setPage] = useState(1); const [q, setQ] = useState(""); const [form, setForm] = useState(false);
  const canPropose = edit || has("PRESIDENT", "SECRETARY", "TREASURER", "MEMBER");
  const load = useCallback(() => api<Paged<P>>(`/committee/proposals?${new URLSearchParams({ page: String(page), size: String(SIZE), q })}`).then(setD), [page, q]);
  useEffect(() => { load(); }, [load]);
  const act = async (id: number, path: string, body?: unknown) => { try { await api(`/committee/proposals/${id}/${path}`, { method: "POST", body }); load(); } catch (e: any) { toast(e.message); } };
  return <>
    <p className="muted small" style={{ marginTop: 0 }}>{t("vt.rule")}</p>
    <div className="toolbar"><input className="input" placeholder={t("vt.search")} aria-label={t("vt.search")} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />{canPropose && <Btn onClick={() => setForm(true)}>{t("vt.new")}</Btn>}</div>
    {!d ? <p className="muted">{t("common.loading")}</p> : d.items.length === 0 ? <Card><Empty>{t("vt.empty")}</Empty></Card> :
      <div className="stack">{d.items.map((p) => (<Card key={p.id}>
        <div className="row wrap" style={{ gap: 8, marginBottom: 6 }}><Chip tone={p.status === "open" ? "info" : "mute"}>{t(p.status === "open" ? "vt.open" : "vt.closed")}</Chip>{p.status === "closed" && <Chip tone={p.result === "approved" ? "ok" : p.result === "rejected" ? "bad" : "warn"}>{t(`vt.res.${p.result}`)}</Chip>}</div>
        <h3 style={{ margin: 0 }}>{p.title}</h3><span className="small muted">{t("vt.by", { n: p.created_by })} · {fdate(p.created_at)}</span>
        {p.text && <p style={{ whiteSpace: "pre-wrap" }}>{p.text}</p>}
        <p className="small"><b>{t("vt.tally", { a: p.tally.approve, r: p.tally.reject, n: p.tally.approve + p.tally.reject, e: p.tally.eligible })}</b>{p.my_vote ? ` · ${t("vt.you", { v: t(`vt.${p.my_vote}`) })}` : ""}</p>
        <div className="row wrap">{p.can_vote && <><Btn size="sm" onClick={() => act(p.id, "vote", { choice: "approve" })}>{t("vt.approve")}</Btn><Btn size="sm" variant="outline" onClick={() => act(p.id, "vote", { choice: "reject" })}>{t("vt.reject")}</Btn></>}
          {edit && p.status === "open" && <Btn size="sm" variant="soft" onClick={() => act(p.id, "close")}>{t("vt.close")}</Btn>}</div>
        {p.votes.length > 0 && <div className="small muted" style={{ marginTop: 8 }}>{t("vt.voted")}: {p.votes.map((v) => `${v.name} (${t(`vt.${v.choice}`)})`).join(", ")}</div>}
      </Card>))}</div>}
    {d && <Pager page={page} size={SIZE} total={d.total} onPage={setPage} />}
    {form && <ProposalForm onClose={() => setForm(false)} onDone={() => { setForm(false); toast(t("rq.saved")); load(); }} />}
  </>;
}

function ProposalForm({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [f, setF] = useState({ title: "", text: "" }); const [err, setErr] = useState("");
  return <Modal title={t("vt.new")} onClose={onClose}>
    <Field label={t("vt.f.title")}><input className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
    <Field label={t("vt.f.text")}><textarea className="input" rows={4} value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} /></Field>
    {err && <p className="error" role="alert">{err}</p>}
    <div className="row"><Btn disabled={f.title.trim().length < 3} onClick={async () => { try { await api("/committee/proposals", { body: f }); onDone(); } catch (e: any) { setErr(e.message); } }}>{t("vt.new")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}
