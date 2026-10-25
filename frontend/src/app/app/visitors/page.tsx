"use client";
import { ExportButton } from "@/components/ExportButton";
import { useCallback, useEffect, useRef, useState } from "react";
import { Btn, Card, Chip, Empty, Field, Modal, PageHead, Stat, Tabs, useToast } from "@/components/ui";
import { Pager } from "@/components/pager";
import { api, fdate, ftime, store } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

const PURPOSES = ["guest", "delivery", "courier", "service", "cab", "official", "other"];
const FREQ = ["maid", "driver", "tutor", "cook", "other"];
const STATUSES = ["waiting", "approved", "denied", "in", "out", "cancelled"];
const TONE: Record<string, "ok" | "warn" | "info" | "mute" | "bad"> = { waiting: "warn", approved: "info", denied: "bad", in: "ok", out: "mute", cancelled: "mute", active: "ok", used: "mute", expired: "bad" };
const POLL_MS = 10000;

type V = { id: number; unit_id: number; unit: string; name: string; phone: string; purpose: string; people: number; vehicle: string; kind: string; status: string; via: string; note?: string; created_at: string; decided_at: string | null; in_at: string | null; out_at: string | null; overstay?: boolean; photo?: boolean; can_decide?: boolean };
type Board = { waiting: V[]; approved: V[]; inside: V[]; denied: V[]; counts: Counts };
type Counts = { today: number; inside: number; waiting: number; overstay: number; overstay_vehicles: number; vehicles_inside: number; overstay_hours: number };
type Paged<T> = { items: T[]; total: number; page: number; size: number };
type Flat = { id: number; number: string };
type Pass = { id: number; unit: string; name: string; purpose: string; people: number; vehicle: string; valid_from: string; valid_to: string; status: string; used_at: string | null };
type Freq = { id: number; unit: string; name: string; phone: string; role: string; valid_from: string; valid_to: string; valid_today: boolean };
type Note = { id: number; kind: string; at: string; read: boolean; visit: V };

/** Runs `fn` now and every 10 seconds while the tab is visible. */
function usePoll(fn: () => void, deps: unknown[]) {
  const ref = useRef(fn); ref.current = fn;
  useEffect(() => {
    ref.current();
    const id = setInterval(() => { if (document.visibilityState === "visible") ref.current(); }, POLL_MS);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
const localInput = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
const minutesSince = (iso?: string | null) => (iso ? Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000)) : 0);

function useSince() {
  const { t } = useT();
  return (iso?: string | null) => { const m = minutesSince(iso); return m < 60 ? t("vs.min", { n: m }) : t("vs.hrmin", { h: Math.floor(m / 60), m: m % 60 }); };
}

function Photo({ id, size = 64 }: { id: number; size?: number }) {
  const [src, setSrc] = useState(""); const [big, setBig] = useState(false); const { t } = useT();
  useEffect(() => {
    let url = ""; let dead = false;
    fetch(`/api/visitors/visits/${id}/photo`, { headers: { Authorization: `Bearer ${store.token}`, "X-Property-Id": String(store.prop) } })
      .then((r) => (r.ok ? r.blob() : null)).then((b) => { if (b && !dead) { url = URL.createObjectURL(b); setSrc(url); } }).catch(() => {});
    return () => { dead = true; if (url) URL.revokeObjectURL(url); };
  }, [id]);
  if (!src) return null;
  return <>
    {/* eslint-disable-next-line @next/next/no-img-element */}
    <img src={src} alt={t("vs.photo")} onClick={() => setBig(true)} style={{ width: size, height: size, objectFit: "cover", borderRadius: 12, border: "1.5px solid var(--line)", cursor: "zoom-in" }} />
    {big && <Modal title={t("vs.photo")} onClose={() => setBig(false)}>{/* eslint-disable-next-line @next/next/no-img-element */}<img src={src} alt={t("vs.photo")} style={{ width: "100%", borderRadius: 12 }} /></Modal>}
  </>;
}

function FlatPicker({ onPick, picked, autoFocus }: { onPick: (f: Flat | null) => void; picked: Flat | null; autoFocus?: boolean }) {
  const { t } = useT(); const [q, setQ] = useState(""); const [rows, setRows] = useState<Flat[]>([]);
  useEffect(() => { const h = setTimeout(() => { api<Flat[]>(`/visitors/flats?q=${encodeURIComponent(q)}`).then(setRows).catch(() => setRows([])); }, 200); return () => clearTimeout(h); }, [q]);
  if (picked) return <div className="row" style={{ gap: 10 }}><Chip tone="info">{t("vs.flat", { n: picked.number })}</Chip><Btn size="sm" variant="ghost" onClick={() => onPick(null)}>{t("vs.change")}</Btn></div>;
  return <div>
    <input className="input" autoFocus={autoFocus} style={{ fontSize: 18, padding: 14 }} placeholder={t("vs.flat_search")} aria-label={t("vs.flat_search")} value={q} onChange={(e) => setQ(e.target.value)} />
    <div className="row wrap" style={{ gap: 8, marginTop: 10, maxHeight: 150, overflowY: "auto" }}>{rows.map((f) => <Btn key={f.id} variant="soft" onClick={() => onPick(f)}>{f.number}</Btn>)}</div>
  </div>;
}

export default function Visitors() {
  const { t } = useT(); const { has, roles } = useAuth();
  const gate = has("GUARD", "CARETAKER", "PROPERTY_ADMIN", "AGENCY_MANAGER");
  const resident = roles.some((r) => ["FLAT_OWNER", "TENANT", "OWNER_REP"].includes(r));   // the resident tabs call endpoints that only residents may use, so staff acting for a building do not get them
  const log = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY", "TREASURER", "MEMBER");
  const tabs = [...(gate ? [{ id: "gate", label: t("vs.tab.gate") }] : []), ...(resident ? [{ id: "mine", label: t("vs.tab.mine") }] : []), ...(log ? [{ id: "log", label: t("vs.tab.log") }] : [])];
  const first = tabs[0]?.id ?? "gate";
  const [tab, setTab] = useState<string>(""); const cur = tabs.some((x) => x.id === tab) ? tab : first;
  return (<>
    <PageHead helpKey="visitor-gate" title={t("vs.title")} sub={t(cur === "gate" ? "vs.sub_gate" : cur === "mine" ? "vs.sub_mine" : "vs.sub_log")} actions={cur === "log" && log ? <ExportButton name="visitors" /> : undefined} />
    {tabs.length > 1 && <div style={{ marginBottom: 14 }}><Tabs value={cur} onChange={setTab} items={tabs} /></div>}
    {cur === "gate" && gate && <Gate />}
    {cur === "mine" && resident && <Mine />}
    {cur === "log" && log && <LogTab />}
    {tabs.length === 0 && <Card><Empty>{t("vs.no_role")}</Empty></Card>}
  </>);
}

/* ------------------------------------------------------------------ the guard desk */

function VisitCard({ v, children, tone }: { v: V; children?: React.ReactNode; tone?: string }) {
  const { t } = useT(); const since = useSince();
  return <Card style={{ borderColor: tone, padding: 16 }}>
    <div className="row" style={{ gap: 14, alignItems: "flex-start" }}>
      {v.photo && <Photo id={v.id} />}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="row wrap" style={{ gap: 8, marginBottom: 6 }}><Chip tone="info">{t("vs.flat", { n: v.unit })}</Chip><Chip tone="mute">{t(`vs.purpose.${v.purpose}`)}</Chip>
          {v.kind !== "walkin" && <Chip tone="mute">{t(`vs.kind.${v.kind}`)}</Chip>}{v.overstay && <Chip tone="bad">{t("vs.overstay")}</Chip>}</div>
        <h3 style={{ margin: 0, fontSize: 20 }}>{v.name}</h3>
        <span className="small muted">{t("vs.people", { n: v.people })}{v.vehicle ? ` · ${v.vehicle}` : ""} · {v.status === "in" ? t("vs.inside_for", { d: since(v.in_at) }) : t("vs.arrived", { d: since(v.created_at) })}</span>
        {v.note ? <div className="small" style={{ marginTop: 4 }}>{t("vs.note")}: {v.note}</div> : null}
      </div></div>
    {children && <div className="row wrap" style={{ marginTop: 12, gap: 10 }}>{children}</div>}
  </Card>;
}

function Gate() {
  const { t } = useT(); const { has } = useAuth(); const toast = useToast();
  const canBeatDenial = has("CARETAKER", "PROPERTY_ADMIN", "AGENCY_MANAGER");
  const [board, setBoard] = useState<Board | null>(null); const [modal, setModal] = useState<"" | "new" | "delivery" | "code" | "freq">(""); const [over, setOver] = useState<V | null>(null);
  const [logTick, setLogTick] = useState(0); const [err, setErr] = useState("");
  const load = useCallback(() => { api<Board>("/visitors/board").then((b) => { setBoard(b); setErr(""); }).catch((e) => setErr(e.message)); }, []);
  usePoll(load, []);
  const act = async (path: string, ok?: string, body?: unknown) => { try { await api(`/visitors/${path}`, { method: "POST", body }); if (ok) toast.show(ok); load(); setLogTick((n) => n + 1); } catch (e: any) { toast.show(e.message); } };
  const done = (msg: string) => { setModal(""); toast.show(msg); load(); setLogTick((n) => n + 1); };
  const big = { minHeight: 72, fontSize: 19 } as const;
  return (<>
    {err && <p className="error" role="alert">{err}</p>}
    <div className="grid g4" style={{ marginBottom: 16 }}>
      <Stat label={t("vs.s.today")} value={board?.counts.today ?? "–"} /><Stat label={t("vs.s.inside")} value={board?.counts.inside ?? "–"} />
      <Stat label={t("vs.s.waiting")} value={board?.counts.waiting ?? "–"} /><Stat label={t("vs.s.overstay", { h: board?.counts.overstay_hours ?? 12 })} value={<span style={{ color: board?.counts.overstay ? "var(--bad)" : undefined }}>{board?.counts.overstay ?? "–"}</span>} /></div>
    <div className="grid g4" style={{ marginBottom: 20, gap: 12 }}>
      <Btn style={big} onClick={() => setModal("new")}>{t("vs.new")}</Btn>
      <Btn style={big} variant="soft" onClick={() => setModal("delivery")}>{t("vs.delivery")}</Btn>
      <Btn style={big} variant="outline" onClick={() => setModal("code")}>{t("vs.code")}</Btn>
      <Btn style={big} variant="ghost" onClick={() => setModal("freq")}>{t("vs.freq")}</Btn></div>
    <p className="small muted" style={{ marginTop: -8 }}>{t("vs.live")}</p>
    {board && board.denied.length > 0 && <Section title={t("vs.sec.denied")}>{board.denied.map((v) => (
      <VisitCard key={v.id} v={v} tone="var(--bad)"><Chip tone="bad">{t("vs.st.denied")}</Chip>
        {canBeatDenial ? <Btn variant="outline" onClick={() => setOver(v)}>{t("vs.override")}</Btn> : <span className="small muted">{t("vs.denied_hint")}</span>}</VisitCard>))}</Section>}
    <Section title={t("vs.sec.waiting")} count={board?.waiting.length}>{board?.waiting.length ? board.waiting.map((v) => (
      <VisitCard key={v.id} v={v} tone="var(--warn)"><Chip tone="warn">{t("vs.wait_resident")}</Chip>
        <Btn variant="outline" onClick={() => setOver(v)}>{t("vs.override")}</Btn><Btn variant="ghost" onClick={() => act(`visits/${v.id}/cancel`, t("vs.cancelled"))}>{t("common.cancel")}</Btn></VisitCard>))
      : <Card><Empty>{t("vs.none_waiting")}</Empty></Card>}</Section>
    {board && board.approved.length > 0 && <Section title={t("vs.sec.approved")} count={board.approved.length}>{board.approved.map((v) => (
      <VisitCard key={v.id} v={v} tone="var(--ok)"><Btn style={{ minHeight: 60, flex: 1, fontSize: 18 }} onClick={() => act(`visits/${v.id}/in`, t("vs.marked_in"))}>{t("vs.mark_in")}</Btn>
        <Btn variant="ghost" onClick={() => act(`visits/${v.id}/cancel`, t("vs.cancelled"))}>{t("common.cancel")}</Btn></VisitCard>))}</Section>}
    <Section title={t("vs.sec.inside")} count={board?.inside.length}>{board?.inside.length ? board.inside.map((v) => (
      <VisitCard key={v.id} v={v} tone={v.overstay ? "var(--bad)" : undefined}><Btn style={{ minHeight: 60, flex: 1, fontSize: 18 }} variant={v.overstay ? "danger" : "soft"} onClick={() => act(`visits/${v.id}/out`, t("vs.marked_out"))}>{t("vs.mark_out")}</Btn></VisitCard>))
      : <Card><Empty>{t("vs.none_inside")}</Empty></Card>}</Section>
    <h2 style={{ margin: "26px 0 10px" }}>{t("vs.day_log")}</h2>
    <VisitList tick={logTick} guardView />
    {modal === "new" && <NewVisit onClose={() => setModal("")} onDone={done} />}
    {modal === "delivery" && <Delivery onClose={() => setModal("")} onDone={done} />}
    {modal === "code" && <CodeEntry onClose={() => setModal("")} onDone={done} />}
    {modal === "freq" && <FreqGate onClose={() => setModal("")} onDone={done} />}
    {over && <Override v={over} onClose={() => setOver(null)} onDone={() => { setOver(null); toast.show(t("vs.overridden")); load(); setLogTick((n) => n + 1); }} />}
    {toast.node}
  </>);
}

function Section({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
  return <section style={{ marginBottom: 18 }}><h2 style={{ margin: "0 0 10px", fontSize: 18 }}>{title}{count !== undefined ? ` (${count})` : ""}</h2><div className="stack" style={{ display: "grid", gap: 12 }}>{children}</div></section>;
}

function NewVisit({ onClose, onDone }: { onClose: () => void; onDone: (m: string) => void }) {
  const { t } = useT(); const [flat, setFlat] = useState<Flat | null>(null); const [f, setF] = useState({ name: "", phone: "", purpose: "guest", people: 1, vehicle: "" }); const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const go = async () => {
    if (!flat) return; setBusy(true); setErr("");
    try {
      const v = await api<V & { notified: number }>("/visitors/visits", { body: { ...f, unit_id: flat.id } });
      if (file) {
        const fd = new FormData(); fd.append("file", file);
        const r = await fetch(`/api/visitors/visits/${v.id}/photo`, { method: "POST", body: fd, headers: { Authorization: `Bearer ${store.token}`, "X-Property-Id": String(store.prop) } });
        if (!r.ok) { const j = await r.json().catch(() => ({})); onDone(`${t("vs.sent")} ${t("vs.photo_failed")}: ${j.detail ?? ""}`); return; }
      }
      onDone(v.notified ? t("vs.sent") : t("vs.sent_nobody"));
    } catch (e: any) { setErr(e.message); setBusy(false); }
  };
  return <Modal title={t("vs.new")} onClose={onClose}>
    <Field label={t("vs.f.flat")}><FlatPicker picked={flat} onPick={setFlat} autoFocus /></Field>
    <Field label={t("vs.f.name")}><input className="input" style={{ fontSize: 18, padding: 14 }} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
    <Field label={t("vs.f.purpose")}><div className="row wrap" style={{ gap: 8 }}>{PURPOSES.map((p) => <Btn key={p} variant={f.purpose === p ? "primary" : "ghost"} onClick={() => setF({ ...f, purpose: p })}>{t(`vs.purpose.${p}`)}</Btn>)}</div></Field>
    <div className="grid g2" style={{ gap: 12 }}>
      <Field label={t("vs.f.people")}><input className="input" type="number" min={1} max={50} value={f.people} onChange={(e) => setF({ ...f, people: Math.max(1, Number(e.target.value) || 1) })} /></Field>
      <Field label={t("vs.f.phone")} hint={t("vs.optional")}><input className="input" inputMode="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field></div>
    <Field label={t("vs.f.vehicle")} hint={t("vs.optional")}><input className="input" value={f.vehicle} onChange={(e) => setF({ ...f, vehicle: e.target.value })} /></Field>
    <Field label={t("vs.f.photo")} hint={t("vs.photo_hint")}><input className="input" type="file" accept="image/jpeg,image/png" capture="environment" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
    {err && <p className="error" role="alert">{err}</p>}
    <div className="row"><Btn size="lg" onClick={go} disabled={busy || !flat || f.name.trim().length < 2}>{t("vs.send")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}

function Delivery({ onClose, onDone }: { onClose: () => void; onDone: (m: string) => void }) {
  const { t } = useT(); const [name, setName] = useState(""); const [q, setQ] = useState(""); const [rows, setRows] = useState<Flat[]>([]); const [err, setErr] = useState("");
  useEffect(() => { const h = setTimeout(() => { api<Flat[]>(`/visitors/flats?q=${encodeURIComponent(q)}`).then(setRows).catch(() => {}); }, 200); return () => clearTimeout(h); }, [q]);
  const send = async (f: Flat) => { try { await api("/visitors/visits/delivery", { body: { unit_id: f.id, name: name.trim() || t("vs.purpose.delivery") } }); onDone(t("vs.delivery_sent", { n: f.number })); } catch (e: any) { setErr(e.message); } };
  return <Modal title={t("vs.delivery")} onClose={onClose}>
    <p className="muted" style={{ marginTop: 0 }}>{t("vs.delivery_help")}</p>
    <Field label={t("vs.f.name")} hint={t("vs.optional")}><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder={t("vs.delivery_ph")} /></Field>
    <Field label={t("vs.f.flat")}><input className="input" autoFocus style={{ fontSize: 18, padding: 14 }} placeholder={t("vs.flat_search")} value={q} onChange={(e) => setQ(e.target.value)} /></Field>
    <div className="row wrap" style={{ gap: 8, maxHeight: 220, overflowY: "auto" }}>{rows.map((f) => <Btn key={f.id} size="lg" variant="soft" onClick={() => send(f)}>{f.number}</Btn>)}</div>
    {err && <p className="error" role="alert">{err}</p>}</Modal>;
}

function CodeEntry({ onClose, onDone }: { onClose: () => void; onDone: (m: string) => void }) {
  const { t } = useT(); const [code, setCode] = useState(""); const [err, setErr] = useState("");
  const go = async () => { setErr(""); try { const v = await api<V>("/visitors/passes/redeem", { body: { code } }); onDone(t("vs.code_ok", { n: v.name, f: v.unit })); } catch (e: any) { setErr(e.message); setCode(""); } };
  return <Modal title={t("vs.code")} onClose={onClose}>
    <p className="muted" style={{ marginTop: 0 }}>{t("vs.code_help")}</p>
    <input className="input" autoFocus inputMode="numeric" pattern="[0-9]*" maxLength={6} aria-label={t("vs.code")} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
      onKeyDown={(e) => e.key === "Enter" && code.length === 6 && go()} style={{ fontSize: 36, letterSpacing: "0.4em", textAlign: "center", padding: 16 }} />
    {err && <p className="error" role="alert">{err}</p>}
    <div className="row" style={{ marginTop: 14 }}><Btn size="lg" disabled={code.length !== 6} onClick={go}>{t("vs.code_go")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}

function FreqGate({ onClose, onDone }: { onClose: () => void; onDone: (m: string) => void }) {
  const { t } = useT(); const [q, setQ] = useState(""); const [page, setPage] = useState(1); const [data, setData] = useState<Paged<Freq> | null>(null); const [err, setErr] = useState("");
  useEffect(() => { api<Paged<Freq>>(`/visitors/frequent?page=${page}&q=${encodeURIComponent(q)}`).then(setData); }, [page, q]);
  const go = async (f: Freq) => { try { await api(`/visitors/frequent/${f.id}/enter`, { method: "POST" }); onDone(t("vs.freq_ok", { n: f.name })); } catch (e: any) { setErr(e.message); } };
  return <Modal title={t("vs.freq")} onClose={onClose}>
    <input className="input" autoFocus placeholder={t("vs.freq_search")} aria-label={t("vs.freq_search")} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
    <div style={{ margin: "12px 0" }}>{!data ? <p className="muted">{t("common.loading")}</p> : data.items.length === 0 ? <Empty>{t("vs.freq_none_gate")}</Empty> : data.items.map((f) => (
      <div key={f.id} className="row between" style={{ padding: "10px 0", borderTop: "1px solid var(--line)", gap: 10 }}>
        <div><b>{f.name}</b><br /><span className="small muted">{t(`vs.role.${f.role}`)} · {t("vs.flat", { n: f.unit })}</span></div>
        <Btn onClick={() => go(f)}>{t("vs.wave")}</Btn></div>))}</div>
    {data && <Pager page={page} size={data.size} total={data.total} onPage={setPage} />}
    {err && <p className="error" role="alert">{err}</p>}</Modal>;
}

function Override({ v, onClose, onDone }: { v: V; onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [note, setNote] = useState(""); const [err, setErr] = useState("");
  const go = async () => { try { await api(`/visitors/visits/${v.id}/override`, { body: { note } }); onDone(); } catch (e: any) { setErr(e.message); } };
  return <Modal title={t("vs.override")} onClose={onClose}>
    <p style={{ marginTop: 0 }}><b>{v.name}</b> · {t("vs.flat", { n: v.unit })}</p><p className="muted">{t("vs.override_help")}</p>
    <Field label={t("vs.override_reason")}><input className="input" autoFocus value={note} onChange={(e) => setNote(e.target.value)} /></Field>
    {err && <p className="error" role="alert">{err}</p>}
    <div className="row"><Btn onClick={go} disabled={note.trim().length < 3}>{t("vs.override_go")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}

/** Paged log with search. Used on the gate (today) and in the admin log (any day). */
function VisitList({ tick, guardView }: { tick?: number; guardView?: boolean }) {
  const { t } = useT(); const { prop } = useAuth();
  const [page, setPage] = useState(1); const [q, setQ] = useState(""); const [flat, setFlat] = useState(""); const [status, setStatus] = useState(""); const [purpose, setPurpose] = useState("");
  const [from, setFrom] = useState(""); const [to, setTo] = useState(""); const [inside, setInside] = useState(false); const [over, setOver] = useState(false); const [data, setData] = useState<Paged<V> | null>(null);
  useEffect(() => {
    const p = new URLSearchParams({ page: String(page) }); if (q) p.set("q", q); if (flat) p.set("flat", flat); if (status) p.set("status", status); if (purpose) p.set("purpose", purpose);
    if (from) p.set("date_from", from); if (to) p.set("date_to", to); if (inside) p.set("inside", "true"); if (over) p.set("overstay", "true");
    api<Paged<V>>(`/visitors/visits?${p}`).then(setData);
  }, [page, q, flat, status, purpose, from, to, inside, over, tick, prop?.id]);
  const reset = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPage(1); };
  return <>
    <div className="toolbar">
      <input className="input" placeholder={t("vs.search")} aria-label={t("vs.search")} value={q} onChange={(e) => reset(setQ)(e.target.value)} />
      <input className="input" style={{ maxWidth: 130 }} placeholder={t("vs.f.flat")} aria-label={t("vs.f.flat")} value={flat} onChange={(e) => reset(setFlat)(e.target.value)} />
      <select className="input" style={{ maxWidth: 160 }} aria-label={t("vs.f.status")} value={status} onChange={(e) => reset(setStatus)(e.target.value)}><option value="">{t("vs.all")}</option>{STATUSES.map((s) => <option key={s} value={s}>{t(`vs.st.${s}`)}</option>)}</select>
      {!guardView && <>
        <select className="input" style={{ maxWidth: 170 }} aria-label={t("vs.f.purpose")} value={purpose} onChange={(e) => reset(setPurpose)(e.target.value)}><option value="">{t("vs.all")}</option>{PURPOSES.map((s) => <option key={s} value={s}>{t(`vs.purpose.${s}`)}</option>)}</select>
        <input className="input" type="date" style={{ maxWidth: 160 }} aria-label={t("vs.from")} value={from} onChange={(e) => reset(setFrom)(e.target.value)} />
        <input className="input" type="date" style={{ maxWidth: 160 }} aria-label={t("vs.to")} value={to} onChange={(e) => reset(setTo)(e.target.value)} />
        <label className="row"><input type="checkbox" checked={inside} onChange={(e) => reset(setInside)(e.target.checked)} /> {t("vs.only_inside")}</label>
        <label className="row"><input type="checkbox" checked={over} onChange={(e) => reset(setOver)(e.target.checked)} /> {t("vs.only_overstay")}</label></>}
    </div>
    {!data ? <p className="muted">{t("common.loading")}</p> : data.items.length === 0 ? <Card><Empty>{t("vs.empty")}</Empty></Card> :
      <div className="stack">{data.items.map((v) => (
        <Card key={v.id} style={{ padding: 14, borderColor: v.overstay ? "var(--bad)" : undefined }}>
          <div className="row between wrap" style={{ gap: 12 }}>
            <div className="row" style={{ gap: 12, flex: 1, minWidth: 220 }}>{v.photo && <Photo id={v.id} size={48} />}
              <div><div className="row wrap" style={{ gap: 8, marginBottom: 4 }}><Chip tone={TONE[v.status]}>{t(`vs.st.${v.status}`)}</Chip><Chip tone="info">{t("vs.flat", { n: v.unit })}</Chip><Chip tone="mute">{t(`vs.purpose.${v.purpose}`)}</Chip>{v.overstay && <Chip tone="bad">{t("vs.overstay")}</Chip>}{v.via === "override" && <Chip tone="warn">{t("vs.override_tag")}</Chip>}</div>
                <b>{v.name}</b> <span className="small muted">· {t("vs.people", { n: v.people })}{v.vehicle ? ` · ${v.vehicle}` : ""}{v.phone ? ` · ${v.phone}` : ""}</span></div></div>
            <div className="small muted" style={{ textAlign: "right" }}>{ftime(v.created_at)}{v.in_at ? <><br />{t("vs.in")} {ftime(v.in_at)}</> : null}{v.out_at ? <><br />{t("vs.out")} {ftime(v.out_at)}</> : null}</div></div>
          {v.note ? <div className="small muted" style={{ marginTop: 6 }}>{t("vs.note")}: {v.note}</div> : null}
        </Card>))}</div>}
    {data && <Pager page={page} size={data.size} total={data.total} onPage={setPage} />}
  </>;
}

/* ------------------------------------------------------------------ admin and committee */

function LogTab() {
  const { t } = useT(); const { has } = useAuth(); const toast = useToast();
  const canEdit = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY");
  const [sum, setSum] = useState<Counts | null>(null); const [set, setSet] = useState<{ page_size: number; overstay_hours: number } | null>(null); const [edit, setEdit] = useState({ page_size: "10", overstay_hours: "12" }); const [tick, setTick] = useState(0);
  useEffect(() => { api<Counts>("/visitors/summary").then(setSum); api<{ page_size: number; overstay_hours: number }>("/visitors/settings").then((s) => { setSet(s); setEdit({ page_size: String(s.page_size), overstay_hours: String(s.overstay_hours) }); }); }, [tick]);
  const save = async () => { try { await api("/visitors/settings", { method: "PUT", body: { page_size: Number(edit.page_size), overstay_hours: Number(edit.overstay_hours) } }); toast.show(t("vs.saved")); setTick((n) => n + 1); } catch (e: any) { toast.show(e.message); } };
  return (<>
    {sum && <div className="grid g4" style={{ marginBottom: 16 }}>
      <Stat label={t("vs.s.today")} value={sum.today} /><Stat label={t("vs.s.inside")} value={sum.inside} note={t("vs.s.vehicles", { n: sum.vehicles_inside })} />
      <Stat label={t("vs.s.overstay", { h: sum.overstay_hours })} value={<span style={{ color: sum.overstay ? "var(--bad)" : undefined }}>{sum.overstay}</span>} note={t("vs.s.vehicles", { n: sum.overstay_vehicles })} />
      <Stat label={t("vs.s.waiting")} value={sum.waiting} /></div>}
    <VisitList tick={tick} />
    {set && <Card style={{ marginTop: 18 }}><h3>{t("vs.settings")}</h3>
      <div className="row wrap" style={{ gap: 12, alignItems: "flex-end" }}>
        <Field label={t("vs.page_size")}><input className="input" type="number" min={5} max={100} style={{ width: 110 }} disabled={!canEdit} value={edit.page_size} onChange={(e) => setEdit({ ...edit, page_size: e.target.value })} /></Field>
        <Field label={t("vs.overstay_hours")}><input className="input" type="number" min={1} max={72} style={{ width: 110 }} disabled={!canEdit} value={edit.overstay_hours} onChange={(e) => setEdit({ ...edit, overstay_hours: e.target.value })} /></Field>
        {canEdit && <Btn variant="soft" onClick={save}>{t("vs.save")}</Btn>}</div></Card>}
    {toast.node}
  </>);
}

/* ------------------------------------------------------------------ residents */

function Mine() {
  const { t } = useT(); const toast = useToast();
  const [sub, setSub] = useState<"now" | "expected" | "freq" | "history">("now");
  const [pend, setPend] = useState<{ waiting: V[]; unread: number } | null>(null);
  const load = useCallback(() => { api<{ waiting: V[]; unread: number }>("/visitors/mine/pending").then(setPend).catch(() => {}); }, []);
  usePoll(load, []);
  return (<>
    <div style={{ marginBottom: 14 }}><Tabs value={sub} onChange={setSub} items={[{ id: "now", label: t("vs.sub.now") + (pend?.unread ? ` (${pend.unread})` : "") }, { id: "expected", label: t("vs.sub.expected") }, { id: "freq", label: t("vs.sub.freq") }, { id: "history", label: t("vs.sub.history") }]} /></div>
    {sub === "now" && <Now pend={pend} reload={load} toast={toast.show} />}
    {sub === "expected" && <Expected toast={toast.show} />}
    {sub === "freq" && <Frequent toast={toast.show} />}
    {sub === "history" && <History />}
    {toast.node}
  </>);
}

function Now({ pend, reload, toast }: { pend: { waiting: V[]; unread: number } | null; reload: () => void; toast: (m: string) => void }) {
  const { t } = useT(); const since = useSince(); const [page, setPage] = useState(1); const [data, setData] = useState<Paged<Note> | null>(null); const [tick, setTick] = useState(0);
  useEffect(() => { api<Paged<Note>>(`/visitors/mine/notifications?page=${page}`).then(setData).catch(() => setData(null)); }, [page, tick, pend?.unread]);
  const decide = async (v: V, approve: boolean) => { try { await api(`/visitors/visits/${v.id}/decision`, { body: { approve } }); toast(t(approve ? "vs.approved_ok" : "vs.denied_ok")); reload(); setTick((n) => n + 1); } catch (e: any) { toast(e.message); reload(); } };
  return <>
    <p className="small muted">{t("vs.live_mine")}</p>
    {pend && pend.waiting.length > 0 ? <div style={{ display: "grid", gap: 12, marginBottom: 20 }}>{pend.waiting.map((v) => (
      <Card key={v.id} style={{ borderColor: "var(--warn)" }}>
        <div className="row wrap" style={{ gap: 8, marginBottom: 6 }}><Chip tone="warn">{t("vs.at_gate")}</Chip><Chip tone="info">{t("vs.flat", { n: v.unit })}</Chip><Chip tone="mute">{t(`vs.purpose.${v.purpose}`)}</Chip></div>
        {v.photo && <div style={{ marginBottom: 8 }}><Photo id={v.id} size={72} /></div>}
        <h3 style={{ margin: 0, fontSize: 20 }}>{v.name}</h3><span className="small muted">{t("vs.people", { n: v.people })}{v.vehicle ? ` · ${v.vehicle}` : ""}{v.phone ? ` · ${v.phone}` : ""} · {t("vs.arrived", { d: since(v.created_at) })}</span>
        <div className="row" style={{ marginTop: 12, gap: 10 }}><Btn size="lg" style={{ flex: 1 }} onClick={() => decide(v, true)}>{t("vs.approve")}</Btn><Btn size="lg" style={{ flex: 1 }} variant="danger" onClick={() => decide(v, false)}>{t("vs.deny")}</Btn></div></Card>))}</div>
      : <Card style={{ marginBottom: 20 }}><Empty>{t("vs.nobody_waiting")}</Empty></Card>}
    <div className="row between" style={{ margin: "6px 0 10px" }}><h2 style={{ margin: 0, fontSize: 18 }}>{t("vs.notices")}</h2>
      {pend && pend.unread > 0 && <Btn size="sm" variant="ghost" onClick={async () => { await api("/visitors/mine/notifications/read", { method: "POST" }); reload(); setTick((n) => n + 1); }}>{t("vs.mark_read")}</Btn>}</div>
    {!data ? <p className="muted">{t("common.loading")}</p> : data.items.length === 0 ? <Card><Empty>{t("vs.notices_none")}</Empty></Card> :
      <div className="stack">{data.items.map((n) => (
        <Card key={n.id} style={{ padding: 14, borderColor: n.read ? undefined : "var(--primary)" }}>
          <div className="row between wrap" style={{ gap: 10 }}>
            <div><b>{t(`vs.note.${n.kind === "ask" ? "ask" : n.visit.kind}`, { n: n.visit.name })}</b><br /><span className="small muted">{t(`vs.purpose.${n.visit.purpose}`)} · {t("vs.people", { n: n.visit.people })}{n.visit.vehicle ? ` · ${n.visit.vehicle}` : ""}</span></div>
            <div style={{ textAlign: "right" }}><Chip tone={TONE[n.visit.status]}>{t(`vs.st.${n.visit.status}`)}</Chip><br /><span className="small muted">{ftime(n.at)}</span></div></div></Card>))}</div>}
    {data && <Pager page={page} size={data.size} total={data.total} onPage={setPage} />}
  </>;
}

function Expected({ toast }: { toast: (m: string) => void }) {
  const { t } = useT(); const [page, setPage] = useState(1); const [data, setData] = useState<Paged<Pass> | null>(null); const [form, setForm] = useState(false); const [shown, setShown] = useState<{ code: string; name: string } | null>(null); const [tick, setTick] = useState(0);
  useEffect(() => { api<Paged<Pass>>(`/visitors/passes?page=${page}`).then(setData); }, [page, tick]);
  return <>
    <div className="row between wrap" style={{ marginBottom: 12 }}><p className="muted" style={{ margin: 0, flex: 1 }}>{t("vs.exp_help")}</p><Btn onClick={() => setForm(true)}>{t("vs.exp_new")}</Btn></div>
    {!data ? <p className="muted">{t("common.loading")}</p> : data.items.length === 0 ? <Card><Empty>{t("vs.exp_none")}</Empty></Card> :
      <div className="stack">{data.items.map((p) => (
        <Card key={p.id} style={{ padding: 14 }}><div className="row between wrap" style={{ gap: 10 }}>
          <div><div className="row wrap" style={{ gap: 8, marginBottom: 4 }}><Chip tone={TONE[p.status]}>{t(`vs.pass.${p.status}`)}</Chip><Chip tone="mute">{t(`vs.purpose.${p.purpose}`)}</Chip></div><b>{p.name}</b><br />
            <span className="small muted">{ftime(p.valid_from)} → {ftime(p.valid_to)}{p.used_at ? ` · ${t("vs.pass.used_at", { d: ftime(p.used_at) })}` : ""}</span></div>
          {p.status === "active" && <Btn size="sm" variant="ghost" onClick={async () => { await api(`/visitors/passes/${p.id}/cancel`, { method: "POST" }); toast(t("vs.exp_cancelled")); setTick((n) => n + 1); }}>{t("vs.exp_cancel")}</Btn>}</div></Card>))}</div>}
    {data && <Pager page={page} size={data.size} total={data.total} onPage={setPage} />}
    {form && <PassForm onClose={() => setForm(false)} onDone={(code, name) => { setForm(false); setShown({ code, name }); setTick((n) => n + 1); }} />}
    {shown && <Modal title={t("vs.exp_code_title")} onClose={() => setShown(null)}>
      <p style={{ marginTop: 0 }}>{t("vs.exp_code_for", { n: shown.name })}</p>
      <div style={{ fontSize: 44, fontWeight: 900, letterSpacing: "0.3em", textAlign: "center", padding: "18px 0", background: "var(--surface2)", borderRadius: 14, border: "1.5px solid var(--line)" }}>{shown.code}</div>
      <p className="small muted" style={{ marginTop: 12 }}>{t("vs.exp_code_once")}</p><Btn onClick={() => setShown(null)}>{t("vs.done")}</Btn></Modal>}
  </>;
}

function PassForm({ onClose, onDone }: { onClose: () => void; onDone: (code: string, name: string) => void }) {
  const { t } = useT(); const [f, setF] = useState({ name: "", purpose: "guest", people: 1, vehicle: "", from: localInput(new Date()), to: localInput(new Date(Date.now() + 3 * 3600000)) }); const [err, setErr] = useState("");
  const go = async () => { try { const r = await api<{ code: string }>("/visitors/passes", { body: { name: f.name, purpose: f.purpose, people: f.people, vehicle: f.vehicle, valid_from: new Date(f.from).toISOString(), valid_to: new Date(f.to).toISOString() } }); onDone(r.code, f.name); } catch (e: any) { setErr(e.message); } };
  return <Modal title={t("vs.exp_new")} onClose={onClose}>
    <Field label={t("vs.f.name")}><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
    <Field label={t("vs.f.purpose")}><select className="input" value={f.purpose} onChange={(e) => setF({ ...f, purpose: e.target.value })}>{PURPOSES.map((p) => <option key={p} value={p}>{t(`vs.purpose.${p}`)}</option>)}</select></Field>
    <div className="grid g2" style={{ gap: 12 }}>
      <Field label={t("vs.exp_from")}><input className="input" type="datetime-local" value={f.from} onChange={(e) => setF({ ...f, from: e.target.value })} /></Field>
      <Field label={t("vs.exp_to")}><input className="input" type="datetime-local" value={f.to} onChange={(e) => setF({ ...f, to: e.target.value })} /></Field>
      <Field label={t("vs.f.people")}><input className="input" type="number" min={1} max={50} value={f.people} onChange={(e) => setF({ ...f, people: Math.max(1, Number(e.target.value) || 1) })} /></Field>
      <Field label={t("vs.f.vehicle")} hint={t("vs.optional")}><input className="input" value={f.vehicle} onChange={(e) => setF({ ...f, vehicle: e.target.value })} /></Field></div>
    {err && <p className="error" role="alert">{err}</p>}
    <div className="row"><Btn onClick={go} disabled={f.name.trim().length < 2 || !f.from || !f.to}>{t("vs.exp_make")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}

function Frequent({ toast }: { toast: (m: string) => void }) {
  const { t } = useT(); const [page, setPage] = useState(1); const [data, setData] = useState<Paged<Freq> | null>(null); const [form, setForm] = useState(false); const [tick, setTick] = useState(0);
  useEffect(() => { api<Paged<Freq>>(`/visitors/frequent?page=${page}`).then(setData); }, [page, tick]);
  return <>
    <div className="row between wrap" style={{ marginBottom: 12 }}><p className="muted" style={{ margin: 0, flex: 1 }}>{t("vs.freq_help")}</p><Btn onClick={() => setForm(true)}>{t("vs.freq_new")}</Btn></div>
    {!data ? <p className="muted">{t("common.loading")}</p> : data.items.length === 0 ? <Card><Empty>{t("vs.freq_none")}</Empty></Card> :
      <div className="stack">{data.items.map((f) => (
        <Card key={f.id} style={{ padding: 14 }}><div className="row between wrap" style={{ gap: 10 }}>
          <div><div className="row wrap" style={{ gap: 8, marginBottom: 4 }}><Chip tone={f.valid_today ? "ok" : "bad"}>{f.valid_today ? t("vs.freq_valid") : t("vs.freq_expired")}</Chip><Chip tone="mute">{t(`vs.role.${f.role}`)}</Chip></div><b>{f.name}</b>{f.phone ? <span className="small muted"> · {f.phone}</span> : null}<br />
            <span className="small muted">{fdate(f.valid_from)} → {fdate(f.valid_to)}</span></div>
          <Btn size="sm" variant="ghost" onClick={async () => { await api(`/visitors/frequent/${f.id}`, { method: "DELETE" }); toast(t("vs.freq_removed")); setTick((n) => n + 1); }}>{t("vs.freq_remove")}</Btn></div></Card>))}</div>}
    {data && <Pager page={page} size={data.size} total={data.total} onPage={setPage} />}
    {form && <FreqForm onClose={() => setForm(false)} onDone={() => { setForm(false); toast(t("vs.freq_added")); setTick((n) => n + 1); }} />}
  </>;
}

function FreqForm({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const today = new Date(); const plus = (d: number) => new Date(today.getTime() + d * 86400000).toISOString().slice(0, 10);
  const [f, setF] = useState({ name: "", phone: "", role: "maid", valid_from: plus(0), valid_to: plus(180) }); const [err, setErr] = useState("");
  const go = async () => { try { await api("/visitors/frequent", { body: f }); onDone(); } catch (e: any) { setErr(e.message); } };
  return <Modal title={t("vs.freq_new")} onClose={onClose}>
    <Field label={t("vs.f.name")}><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
    <Field label={t("vs.f.phone")} hint={t("vs.optional")}><input className="input" inputMode="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
    <Field label={t("vs.f.role")}><select className="input" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{FREQ.map((r) => <option key={r} value={r}>{t(`vs.role.${r}`)}</option>)}</select></Field>
    <div className="grid g2" style={{ gap: 12 }}>
      <Field label={t("vs.valid_from")}><input className="input" type="date" value={f.valid_from} onChange={(e) => setF({ ...f, valid_from: e.target.value })} /></Field>
      <Field label={t("vs.valid_to")}><input className="input" type="date" value={f.valid_to} onChange={(e) => setF({ ...f, valid_to: e.target.value })} /></Field></div>
    {err && <p className="error" role="alert">{err}</p>}
    <div className="row"><Btn onClick={go} disabled={f.name.trim().length < 2}>{t("vs.freq_add")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}

function History() {
  const { t } = useT(); const [page, setPage] = useState(1); const [q, setQ] = useState(""); const [status, setStatus] = useState(""); const [data, setData] = useState<Paged<V> | null>(null);
  useEffect(() => { const p = new URLSearchParams({ page: String(page) }); if (q) p.set("q", q); if (status) p.set("status", status); api<Paged<V>>(`/visitors/mine?${p}`).then(setData); }, [page, q, status]);
  return <>
    <div className="toolbar"><input className="input" placeholder={t("vs.search_name")} aria-label={t("vs.search_name")} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
      <select className="input" style={{ maxWidth: 170 }} aria-label={t("vs.f.status")} value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}><option value="">{t("vs.all")}</option>{STATUSES.map((s) => <option key={s} value={s}>{t(`vs.st.${s}`)}</option>)}</select></div>
    {!data ? <p className="muted">{t("common.loading")}</p> : data.items.length === 0 ? <Card><Empty>{t("vs.empty")}</Empty></Card> :
      <div className="stack">{data.items.map((v) => (
        <Card key={v.id} style={{ padding: 14 }}><div className="row between wrap" style={{ gap: 10 }}>
          <div><div className="row wrap" style={{ gap: 8, marginBottom: 4 }}><Chip tone={TONE[v.status]}>{t(`vs.st.${v.status}`)}</Chip><Chip tone="mute">{t(`vs.purpose.${v.purpose}`)}</Chip>{v.kind !== "walkin" && <Chip tone="mute">{t(`vs.kind.${v.kind}`)}</Chip>}</div>
            <b>{v.name}</b> <span className="small muted">· {t("vs.people", { n: v.people })}{v.vehicle ? ` · ${v.vehicle}` : ""}</span></div>
          <div className="small muted" style={{ textAlign: "right" }}>{ftime(v.created_at)}{v.out_at ? <><br />{t("vs.out")} {ftime(v.out_at)}</> : null}</div></div></Card>))}</div>}
    {data && <Pager page={page} size={data.size} total={data.total} onPage={setPage} />}
  </>;
}
