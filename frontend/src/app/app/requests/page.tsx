"use client";
import { useCallback, useEffect, useState } from "react";
import { Btn, Card, Chip, Empty, Field, Modal, PageHead, Stat, Tabs, useToast } from "@/components/ui";
import { Pager } from "@/components/pager";
import { api, fdate, ftime } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

const CATS = ["lift", "water", "electricity", "security", "cleaning", "noise", "other"];
const STATUSES = ["open", "assigned", "in_progress", "resolved", "closed"];
const TONE: Record<string, "ok" | "warn" | "info" | "mute" | "bad"> = { open: "warn", assigned: "info", in_progress: "info", resolved: "ok", closed: "mute" };
const SIZE = 10;

type R = { id: number; category: string; title: string; text: string; status: string; unit_id: number | null; unit: string; raised_by: string; assignee_id: number | null; assignee: string; created_at: string; due_at: string; sla_hours: number; overdue: boolean; resolved_at: string | null; reopened: number; rating: number | null; rating_note: string };
type Detail = R & { thread: { id: number; by: string; text: string; kind: string; at: string }[]; can_triage: boolean; can_reopen: boolean; can_rate: boolean };
type Page = { items: R[]; total: number; page: number; size: number };
type Sum = { counts: Record<string, number>; overdue: number; total: number; avg_rating: number | null };
type Sla = { category: string; hours: number; default: number };

export default function Requests() {
  const { t } = useT(); const { prop, has } = useAuth(); const toast = useToast();
  const triage = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY", "TREASURER", "MEMBER", "CARETAKER");
  const slaEdit = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY");
  const [tab, setTab] = useState<"list" | "sla">("list"); const [data, setData] = useState<Page | null>(null); const [sum, setSum] = useState<Sum | null>(null);
  const [page, setPage] = useState(1); const [q, setQ] = useState(""); const [status, setStatus] = useState(""); const [cat, setCat] = useState(""); const [late, setLate] = useState(false);
  const [open, setOpen] = useState<number | null>(null); const [form, setForm] = useState(false);
  const load = useCallback(() => {
    const p = new URLSearchParams({ page: String(page), size: String(SIZE) }); if (q) p.set("q", q); if (status) p.set("status", status); if (cat) p.set("category", cat); if (late) p.set("overdue", "true");
    api<Page>(`/requests?${p}`).then(setData); api<Sum>("/requests/summary").then(setSum);
  }, [page, q, status, cat, late]);
  useEffect(() => { load(); }, [load, prop?.id]);
  return (<>
    <PageHead title={t("rq.title")} sub={t(triage ? "rq.sub_staff" : "rq.sub")} actions={<Btn onClick={() => setForm(true)}>{t("rq.new")}</Btn>} />
    {triage && <div style={{ marginBottom: 14 }}><Tabs value={tab} onChange={setTab} items={[{ id: "list", label: t("rq.tab.list") }, { id: "sla", label: t("rq.tab.sla") }]} /></div>}
    {tab === "sla" && triage ? <SlaTab canEdit={slaEdit} onSaved={() => toast.show(t("rq.saved"))} /> : (<>
      {sum && <div className="grid g4" style={{ marginBottom: 16 }}>
        <Stat label={t("rq.total")} value={sum.total} />
        <Stat label={t("rq.st.open")} value={sum.counts.open + sum.counts.assigned + sum.counts.in_progress} />
        <Stat label={t("rq.overdue")} value={<span style={{ color: sum.overdue ? "var(--bad)" : undefined }}>{sum.overdue}</span>} />
        <Stat label={t("rq.avg")} value={sum.avg_rating ?? "–"} /></div>}
      <div className="toolbar">
        <input className="input" placeholder={t("rq.search")} aria-label={t("rq.search")} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <select className="input" aria-label={t("rq.f.category")} style={{ maxWidth: 180 }} value={cat} onChange={(e) => { setCat(e.target.value); setPage(1); }}><option value="">{t("rq.all")}</option>{CATS.map((c) => <option key={c} value={c}>{t(`rq.cat.${c}`)}</option>)}</select>
        <select className="input" aria-label={t("rq.st.open")} style={{ maxWidth: 200 }} value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}><option value="">{t("rq.all")}</option>{STATUSES.map((s) => <option key={s} value={s}>{t(`rq.st.${s}`)}</option>)}</select>
        {triage && <label className="row"><input type="checkbox" checked={late} onChange={(e) => { setLate(e.target.checked); setPage(1); }} /> {t("rq.overdue_only")}</label>}
      </div>
      {!data ? <p className="muted">{t("common.loading")}</p> : data.items.length === 0 ? <Card><Empty>{t("rq.empty")}</Empty></Card> :
        <div className="stack">{data.items.map((r) => (
          <Card key={r.id} style={{ borderColor: r.overdue ? "var(--bad)" : undefined, cursor: "pointer" }}>
            <div className="row between wrap" style={{ gap: 12 }} onClick={() => setOpen(r.id)}>
              <div style={{ flex: 1, minWidth: 220 }}>
                <div className="row wrap" style={{ gap: 8, marginBottom: 6 }}><Chip tone={TONE[r.status]}>{t(`rq.st.${r.status}`)}</Chip><Chip tone="mute">{t(`rq.cat.${r.category}`)}</Chip>{r.overdue && <Chip tone="bad">{t("rq.overdue")}</Chip>}{r.unit && <Chip tone="mute">{t("rq.flat", { n: r.unit })}</Chip>}</div>
                <h3 style={{ margin: 0 }}>{r.title}</h3><span className="small muted">{fdate(r.created_at)} · {t("rq.by", { n: r.raised_by })}{r.assignee ? ` · ${t("rq.assignee")}: ${r.assignee}` : ""}</span></div>
              <div className="small muted" style={{ textAlign: "right" }}>{["open", "assigned", "in_progress"].includes(r.status) ? t("rq.due", { d: ftime(r.due_at) }) : r.rating ? "★".repeat(r.rating) : ""}</div></div>
          </Card>))}</div>}
      {data && <Pager page={page} size={SIZE} total={data.total} onPage={setPage} />}
    </>)}
    {form && <NewRequest onClose={() => setForm(false)} onDone={() => { setForm(false); toast.show(t("rq.raised")); setPage(1); load(); }} />}
    {open && <DetailModal id={open} onClose={() => setOpen(null)} onChange={load} />}
    {toast.node}
  </>);
}

function NewRequest({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [f, setF] = useState({ category: "water", title: "", text: "" }); const [err, setErr] = useState("");
  const go = async () => { try { await api("/requests", { body: f }); onDone(); } catch (e: any) { setErr(e.message); } };
  return <Modal title={t("rq.new")} onClose={onClose}>
    <Field label={t("rq.f.category")}><select className="input" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>{CATS.map((c) => <option key={c} value={c}>{t(`rq.cat.${c}`)}</option>)}</select></Field>
    <Field label={t("rq.f.title")} hint={t("rq.f.hint")}><input className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
    <Field label={t("rq.f.text")}><textarea className="input" rows={4} value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} /></Field>
    {err && <p className="error" role="alert">{err}</p>}
    <div className="row"><Btn onClick={go} disabled={f.title.trim().length < 3}>{t("rq.new")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}

function DetailModal({ id, onClose, onChange }: { id: number; onClose: () => void; onChange: () => void }) {
  const { t } = useT(); const [d, setD] = useState<Detail | null>(null); const [staff, setStaff] = useState<{ id: number; name: string; name_bn: string }[]>([]); const [who, setWho] = useState("");
  const [text, setText] = useState(""); const [stars, setStars] = useState(0); const [note, setNote] = useState(""); const [err, setErr] = useState("");
  const { pick } = useT();
  const load = useCallback(() => api<Detail>(`/requests/${id}`).then((x) => { setD(x); if (x.can_triage) api<typeof staff>("/requests/assignees").then(setStaff).catch(() => {}); }), [id]);
  useEffect(() => { load(); }, [load]);
  const act = async (path: string, body?: unknown) => { setErr(""); try { await api(`/requests/${id}/${path}`, { method: "POST", body }); await load(); onChange(); } catch (e: any) { setErr(e.message); } };
  if (!d) return null;
  const ev = (c: { text: string }) => { const [k, v = ""] = c.text.split(":"); return k === "assigned" ? t("rq.ev.assigned", { n: v }) : k === "status" ? t("rq.ev.status", { s: t(`rq.st.${v}`) }) : k === "rated" ? t("rq.ev.rated", { n: v }) : t(`rq.ev.${k}`); };
  const live = ["open", "assigned", "in_progress"].includes(d.status);
  return <Modal title={d.title} onClose={onClose}>
    <div className="row wrap" style={{ gap: 8, marginBottom: 10 }}><Chip tone={TONE[d.status]}>{t(`rq.st.${d.status}`)}</Chip><Chip tone="mute">{t(`rq.cat.${d.category}`)}</Chip>{d.overdue && <Chip tone="bad">{t("rq.overdue")}</Chip>}{d.unit && <Chip tone="mute">{t("rq.flat", { n: d.unit })}</Chip>}{d.reopened > 0 && <Chip tone="warn">{t("rq.reopened")}</Chip>}</div>
    {d.text && <p style={{ whiteSpace: "pre-wrap", marginTop: 0 }}>{d.text}</p>}
    <p className="small muted">{t("rq.by", { n: d.raised_by })} · {fdate(d.created_at)} · {t("rq.sla_h", { h: d.sla_hours })}{live ? ` · ${t("rq.due", { d: ftime(d.due_at) })}` : ""}<br />{t("rq.assignee")}: {d.assignee || t("rq.nobody")}</p>
    {d.can_triage && d.status !== "closed" && d.status !== "resolved" && <div className="row wrap" style={{ marginBottom: 12 }}>
      <select className="input" style={{ maxWidth: 240 }} aria-label={t("rq.pick_staff")} value={who} onChange={(e) => setWho(e.target.value)}><option value="">{t("rq.pick_staff")}</option>{staff.map((s) => <option key={s.id} value={s.id}>{pick(s.name, s.name_bn)}</option>)}</select>
      <Btn size="sm" variant="soft" disabled={!who} onClick={() => act("assign", { assignee_id: Number(who) })}>{t("rq.assign")}</Btn>
      {d.status === "assigned" && <Btn size="sm" variant="outline" onClick={() => act("status", { status: "in_progress" })}>{t("rq.start")}</Btn>}
      <Btn size="sm" onClick={() => act("status", { status: "resolved" })}>{t("rq.resolve")}</Btn></div>}
    {d.status === "resolved" && <div className="row wrap" style={{ marginBottom: 12 }}>{(d.can_triage || d.can_reopen) && <Btn size="sm" variant="outline" onClick={() => act("status", { status: "closed" })}>{d.can_triage ? t("rq.close") : t("rq.confirm_close")}</Btn>}</div>}
    {d.can_reopen && <Btn size="sm" variant="ghost" onClick={() => act("reopen")}>{t("rq.reopen")}</Btn>}
    {d.rating ? <p><b>{"★".repeat(d.rating)}</b> {t("rq.rated", { n: d.rating })}{d.rating_note ? ` · ${d.rating_note}` : ""}</p> : d.can_rate && <div style={{ margin: "12px 0" }}><b>{t("rq.rate")}</b>
      <div className="row" style={{ margin: "6px 0" }}>{[1, 2, 3, 4, 5].map((n) => <button key={n} className="icon-btn" aria-label={`${n}`} onClick={() => setStars(n)} style={{ fontSize: 22, color: n <= stars ? "var(--warn)" : "var(--muted)" }}>★</button>)}</div>
      <input className="input" placeholder={t("rq.rate_note")} value={note} onChange={(e) => setNote(e.target.value)} />
      <Btn size="sm" style={{ marginTop: 8 }} disabled={!stars} onClick={() => act("rate", { rating: stars, note })}>{t("rq.rate_send")}</Btn></div>}
    <h3 style={{ marginBottom: 6 }}>{t("rq.thread")}</h3>
    <div style={{ maxHeight: 220, overflowY: "auto" }}>{d.thread.map((c) => (<div key={c.id} style={{ padding: "6px 0", borderTop: "1px solid var(--line)" }}>
      {c.kind === "event" ? <span className="small muted">{ev(c)} · {c.by} · {ftime(c.at)}</span> : <><b className="small">{c.by}</b> <span className="small muted">{ftime(c.at)}</span><div style={{ whiteSpace: "pre-wrap" }}>{c.text}</div></>}</div>))}</div>
    <div className="row" style={{ marginTop: 10 }}><input className="input" placeholder={t("rq.comment")} aria-label={t("rq.comment")} value={text} onChange={(e) => setText(e.target.value)} />
      <Btn size="sm" disabled={!text.trim()} onClick={async () => { await act("comments", { text }); setText(""); }}>{t("rq.send")}</Btn></div>
    {err && <p className="error" role="alert">{err}</p>}
  </Modal>;
}

function SlaTab({ canEdit, onSaved }: { canEdit: boolean; onSaved: () => void }) {
  const { t } = useT(); const [rows, setRows] = useState<Sla[] | null>(null); const [edit, setEdit] = useState<Record<string, string>>({});
  useEffect(() => { api<Sla[]>("/requests/sla").then(setRows); }, []);
  if (!rows) return null;
  return <Card><p className="muted" style={{ marginTop: 0 }}>{t("rq.sla.sub")}</p>
    {rows.map((s) => (<div key={s.category} className="row between wrap" style={{ padding: "10px 0", borderTop: "1px solid var(--line)", gap: 12 }}>
      <div><b>{t(`rq.cat.${s.category}`)}</b> <span className="small muted">· {t("rq.sla.default", { h: s.default })}</span></div>
      <div className="row"><input className="input" type="number" min={1} max={720} aria-label={`${t(`rq.cat.${s.category}`)} ${t("rq.sla.hours")}`} style={{ width: 100 }} disabled={!canEdit} value={edit[s.category] ?? String(s.hours)} onChange={(e) => setEdit({ ...edit, [s.category]: e.target.value })} />
        {canEdit && <Btn size="sm" variant="soft" disabled={edit[s.category] === undefined || Number(edit[s.category]) < 1} onClick={async () => { await api(`/requests/sla/${s.category}`, { method: "PUT", body: { hours: Number(edit[s.category]) } }); setRows(await api<Sla[]>("/requests/sla")); setEdit({}); onSaved(); }}>{t("rq.sla.save")}</Btn>}</div></div>))}</Card>;
}
