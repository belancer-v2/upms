"use client";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Btn, Card, Chip, Empty, Field, Modal, PageHead, Tabs, useToast } from "@/components/ui";
import { Pager } from "@/components/pager";
import { api, fdate, money } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

const SLOTS = ["morning", "evening", "night", "full"] as const;
const PURPOSES = ["wedding_reception", "birthday", "aqeeqah", "milad", "meeting", "other"];
const KINDS = ["hall", "rooftop", "gym", "playground", "guest_room"];
const METHODS = ["cash", "bank", "bkash", "nagad"];
const SIZE = 10;
const CELL: Record<string, { bg: string; fg: string }> = {
  free: { bg: "var(--ok-bg)", fg: "var(--ok)" }, pending: { bg: "var(--warn-bg)", fg: "var(--warn)" }, held: { bg: "var(--info-bg)", fg: "var(--info)" },
  booked: { bg: "var(--bad-bg)", fg: "var(--bad)" }, blackout: { bg: "var(--surface2)", fg: "var(--muted)" },
};
const TONE: Record<string, "ok" | "warn" | "info" | "mute" | "bad"> = { pending: "warn", approved: "info", confirmed: "ok", completed: "mute", rejected: "bad", cancelled: "mute", expired: "mute" };

type Slot = { on: boolean; owner: number; tenant: number };
type Rule = { days: number; pct: number };
type Amenity = { id: number; kind: string; name: string; name_bn: string; capacity: number; rules: string; rules_bn: string; photo_url: string; active: boolean; slots: Record<string, Slot>; slot_hours: Record<string, number[]>;
  ext_hour_fee: number; max_ext_hours: number; deposit: number; cleaning_fee: number; generator_fee: number; free_quota: number; min_notice_days: number; max_advance_days: number; hold_days: number; cancel_rules: Rule[] };
type Cell = { state: string; booking_id: number | null; mine: boolean };
type Day = { date: string; blackout: { reason: string; reason_bn: string } | null; bookable: boolean; past: boolean; slots: Record<string, Cell> };
type Cal = { amenity: Amenity; month: string; days: Day[] };
type Bk = { id: number; amenity_id: number; amenity: string; amenity_bn: string; unit: string; by: string; by_bn: string; party: string; on_date: string; slot: string; hours: number[]; purpose: string; guests: number; catering: boolean; contact: string; note: string;
  ext_hours: number; use_generator: boolean; status: string; reason: string; expires_at: string | null; invoice_id: number | null; invoice_status: string; paid: number; balance: number; fee: number; ext_fee: number; cleaning: number; generator: number; deposit: number; total: number; free_used: boolean;
  damage_amount: number; damage_note: string; refund_amount: number; refund_method: string; refunded_at: string | null; mine: boolean; conflict: boolean;
  can_approve: boolean; can_cancel: boolean; can_handover: boolean; can_refund: boolean; can_permit: boolean };
type Page = { items: Bk[]; total: number; page: number; size: number };
type Blk = { id: number; on_date: string; amenity_id: number | null; reason: string; reason_bn: string };
type Quote = { party: string; rent: number; fee: number; free: boolean; ext_fee: number; cleaning: number; generator: number; deposit: number; total: number };

const hh = (h: number) => `${String(h).padStart(2, "0")}:00`;
const range = (h: number[] | undefined) => (h ? `${hh(h[0])}–${hh(h[1])}` : "");
const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const shiftMonth = (m: string, n: number) => { const [y, mo] = m.split("-").map(Number); return ymd(new Date(y, mo - 1 + n, 1)).slice(0, 7); };

export default function Amenities() {
  const { t, pick } = useT(); const { prop, has } = useAuth(); const toast = useToast();
  const decide = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY");
  const staff = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY", "TREASURER", "MEMBER", "AUDITOR", "CARETAKER", "GUARD");
  const resident = has("FLAT_OWNER", "TENANT", "OWNER_REP");
  const [tab, setTab] = useState<"cal" | "mine" | "queue" | "set">("cal");
  const [list, setList] = useState<Amenity[] | null>(null); const [aid, setAid] = useState(0); const [err, setErr] = useState(""); const [form, setForm] = useState<{ date: string; slot: string } | null>(null);
  const [pending, setPending] = useState(0);
  const loadList = useCallback(() => { api<Amenity[]>("/amenities").then((r) => { setList(r); setAid((x) => x || r.find((a) => a.active)?.id || r[0]?.id || 0); }).catch((e) => setErr(e.message)); if (staff) api<{ pending: number }>("/amenities/summary").then((s) => setPending(s.pending)).catch(() => {}); }, [staff]);
  useEffect(() => { loadList(); }, [loadList, prop?.id]);
  const amenity = list?.find((a) => a.id === aid);
  const tabs = [{ id: "cal" as const, label: t("am.tab.cal") }, ...(resident ? [{ id: "mine" as const, label: t("am.tab.mine") }] : []),
    ...(staff ? [{ id: "queue" as const, label: pending ? `${t("am.tab.queue")} (${pending})` : t("am.tab.queue") }] : []), ...(decide ? [{ id: "set" as const, label: t("am.tab.set") }] : [])];
  if (err) return <><PageHead title={t("am.title")} /><Card><p className="error" role="alert">{err.includes("plan") ? t("am.upgrade") : err}</p></Card></>;
  return (<>
    <PageHead title={t("am.title")} sub={t("am.sub")} actions={resident && amenity ? <Btn onClick={() => setForm({ date: "", slot: "" })}>{t("am.request")}</Btn> : undefined} />
    <div style={{ marginBottom: 14 }}><Tabs value={tab} onChange={setTab} items={tabs} /></div>
    {!list ? <p className="muted">{t("common.loading")}</p> : <>
      {tab === "cal" && <CalendarTab list={list} aid={aid} setAid={setAid} resident={resident} onPick={(d, s) => setForm({ date: d, slot: s })} />}
      {tab === "mine" && <BookingList scope="mine" decide={false} onChange={() => { loadList(); }} toast={toast} amenities={list} />}
      {tab === "queue" && <BookingList scope="all" decide={decide} onChange={loadList} toast={toast} amenities={list} />}
      {tab === "set" && <Settings list={list} onChange={loadList} toast={toast} />}
    </>}
    {form && amenity && <BookingForm amenities={list!.filter((a) => a.active)} first={amenity} init={form} onClose={() => setForm(null)} onDone={() => { setForm(null); toast.show(t("am.sent")); setTab("mine"); loadList(); }} />}
    {toast.node}
  </>);
}

function CalendarTab({ list, aid, setAid, resident, onPick }: { list: Amenity[]; aid: number; setAid: (n: number) => void; resident: boolean; onPick: (d: string, s: string) => void }) {
  const { t, pick, lang } = useT(); const [month, setMonth] = useState(ymd(new Date()).slice(0, 7)); const [cal, setCal] = useState<Cal | null>(null); const [day, setDay] = useState<Day | null>(null);
  useEffect(() => { if (aid) api<Cal>(`/amenities/${aid}/calendar?month=${month}`).then(setCal); }, [aid, month]);
  const pad = useMemo(() => { if (!cal) return 0; const [y, m] = cal.month.split("-").map(Number); return (new Date(y, m - 1, 1).getDay() + 6) % 7; }, [cal]);   // week starts Monday
  const wd = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
  if (!list.length) return <Card><Empty>{t("am.none")}</Empty></Card>;
  const a = cal?.amenity;
  return (<>
    <div className="toolbar">
      <select className="input" aria-label={t("am.f.amenity")} style={{ maxWidth: 260 }} value={aid} onChange={(e) => setAid(Number(e.target.value))}>{list.map((x) => <option key={x.id} value={x.id}>{pick(x.name, x.name_bn)}</option>)}</select>
      <div className="row"><Btn variant="ghost" size="sm" onClick={() => setMonth(shiftMonth(month, -1))}>{t("common.prev")}</Btn><b style={{ minWidth: 110, textAlign: "center" }}>{new Date(`${month}-01T00:00`).toLocaleDateString(lang === "bn" ? "bn-BD" : "en-GB", { month: "long", year: "numeric" })}</b><Btn variant="ghost" size="sm" onClick={() => setMonth(shiftMonth(month, 1))}>{t("common.next")}</Btn></div>
    </div>
    <div className="row wrap small" style={{ gap: 10, marginBottom: 10 }}>{["free", "pending", "held", "booked", "blackout"].map((s) => <span key={s} className="row" style={{ gap: 6 }}><i style={{ width: 14, height: 14, borderRadius: 4, background: CELL[s].bg, border: `1px solid ${CELL[s].fg}`, display: "inline-block" }} />{t(`am.state.${s}`)}</span>)}</div>
    {a && <Card style={{ padding: 8 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0, 1fr))", gap: 4 }}>
        {wd.map((w) => <div key={w} className="small muted" style={{ textAlign: "center", fontWeight: 700 }}>{t(`am.wd.${w}`)}</div>)}
        {Array.from({ length: pad }).map((_, i) => <div key={`p${i}`} />)}
        {cal.days.map((d) => (
          <button key={d.date} onClick={() => setDay(d)} aria-label={d.date} style={{ border: "1px solid var(--line)", borderRadius: 10, background: "var(--surface)", color: "var(--text)", padding: "4px 3px", minHeight: 62, opacity: d.past ? 0.55 : 1, cursor: "pointer", textAlign: "center" }}>
            <div className="small" style={{ fontWeight: 800 }}>{Number(d.date.slice(8))}</div>
            {d.blackout ? <div style={{ ...CELL.blackout, background: CELL.blackout.bg, color: CELL.blackout.fg, fontSize: 10, borderRadius: 4, marginTop: 2, textDecoration: "line-through" }}>{t("am.state.blackout")}</div> :
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2, marginTop: 2 }}>{SLOTS.filter((s) => d.slots[s]).map((s) => { const c = d.slots[s]; const k = CELL[c.state]; return <span key={s} style={{ background: k.bg, color: k.fg, fontSize: 10, fontWeight: 800, borderRadius: 4, padding: "1px 0", outline: c.mine ? "2px solid var(--primary)" : undefined }}>{t(`am.slot.s.${s}`)}</span>; })}</div>}
          </button>))}
      </div>
    </Card>}
    {a && <Card style={{ marginTop: 14 }}><h3 style={{ marginTop: 0 }}>{pick(a.name, a.name_bn)}</h3>
      <p className="small muted" style={{ marginTop: 0 }}>{t("am.cap", { n: a.capacity })} · {t("am.notice", { a: a.min_notice_days, b: a.max_advance_days })}</p>
      {(pick(a.rules, a.rules_bn)) && <><b className="small">{t("am.rules")}</b><p style={{ whiteSpace: "pre-wrap", margin: "4px 0 0" }}>{pick(a.rules, a.rules_bn)}</p></>}</Card>}
    {day && a && <Modal title={fdate(day.date)} onClose={() => setDay(null)}>
      {day.blackout && <p><Chip tone="mute">{t("am.state.blackout")}</Chip> {pick(day.blackout.reason, day.blackout.reason_bn)}</p>}
      {!day.blackout && SLOTS.filter((s) => day.slots[s]).map((s) => { const c = day.slots[s]; const sl = a.slots[s]; return (
        <div key={s} className="row between wrap" style={{ padding: "9px 0", borderTop: "1px solid var(--line)", gap: 8 }}>
          <div><b>{t(`am.slot.${s}`)}</b> <span className="small muted">{range(a.slot_hours[s])}</span><div className="small muted">{t("am.rate", { o: money(sl.owner), t: money(sl.tenant) })}</div></div>
          <div className="row"><span className="chip" style={{ background: CELL[c.state].bg, color: CELL[c.state].fg }}>{t(`am.state.${c.state}`)}{c.mine ? ` · ${t("am.mine")}` : ""}</span>
            {resident && c.state === "free" && day.bookable && <Btn size="sm" onClick={() => { onPick(day.date, s); setDay(null); }}>{t("am.request")}</Btn>}</div></div>); })}
      {!day.bookable && !day.blackout && <p className="small muted">{day.past ? t("am.past") : t("am.window", { a: a.min_notice_days, b: a.max_advance_days })}</p>}
    </Modal>}
  </>);
}

function BookingForm({ amenities, first, init, onClose, onDone }: { amenities: Amenity[]; first: Amenity; init: { date: string; slot: string }; onClose: () => void; onDone: () => void }) {
  const { t, pick } = useT(); const [f, setF] = useState({ amenity_id: first.active ? first.id : amenities[0]?.id ?? 0, on_date: init.date, slot: init.slot, purpose: "birthday", guests: 50, catering: false, contact: "", note: "", ext_hours: 0, use_generator: false });
  const a = amenities.find((x) => x.id === f.amenity_id) ?? amenities[0]; const [q, setQ] = useState<Quote | null>(null); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const offered = SLOTS.filter((s) => a?.slots[s]?.on);
  useEffect(() => { if (a && !offered.includes(f.slot as any)) setF((x) => ({ ...x, slot: offered[0] ?? "" })); }, [a?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    setQ(null); if (!a || !f.on_date || !f.slot) return;
    const p = new URLSearchParams({ amenity_id: String(a.id), on_date: f.on_date, slot: f.slot, ext_hours: String(f.ext_hours), generator: String(f.use_generator) });
    api<Quote>(`/amenities/quote?${p}`).then((x) => { setQ(x); setErr(""); }).catch((e) => setErr(e.message));
  }, [a?.id, f.on_date, f.slot, f.ext_hours, f.use_generator]); // eslint-disable-line react-hooks/exhaustive-deps
  const go = async () => { setBusy(true); try { await api("/amenities/bookings", { body: { ...f, guests: Number(f.guests) } }); onDone(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); } };
  const row = (k: string, v: number, show = true) => show && <div className="row between small" style={{ padding: "3px 0" }}><span>{k}</span><span>{money(v)}</span></div>;
  return <Modal title={t("am.request")} onClose={onClose}>
    {amenities.length > 1 && <Field label={t("am.f.amenity")}><select className="input" value={f.amenity_id} onChange={(e) => setF({ ...f, amenity_id: Number(e.target.value) })}>{amenities.map((x) => <option key={x.id} value={x.id}>{pick(x.name, x.name_bn)}</option>)}</select></Field>}
    <div className="grid g2">
      <Field label={t("am.f.date")}><input className="input" type="date" value={f.on_date} onChange={(e) => setF({ ...f, on_date: e.target.value })} /></Field>
      <Field label={t("am.f.slot")}><select className="input" value={f.slot} onChange={(e) => setF({ ...f, slot: e.target.value })}>{offered.map((s) => <option key={s} value={s}>{t(`am.slot.${s}`)} · {range(a?.slot_hours[s])}</option>)}</select></Field></div>
    <div className="grid g2">
      <Field label={t("am.f.purpose")}><select className="input" value={f.purpose} onChange={(e) => setF({ ...f, purpose: e.target.value })}>{PURPOSES.map((p) => <option key={p} value={p}>{t(`am.purpose.${p}`)}</option>)}</select></Field>
      <Field label={t("am.f.guests")} hint={t("am.cap", { n: a?.capacity ?? 0 })}><input className="input" type="number" min={1} max={a?.capacity} value={f.guests} onChange={(e) => setF({ ...f, guests: Number(e.target.value) })} /></Field></div>
    <Field label={t("am.f.contact")}><input className="input" inputMode="tel" value={f.contact} onChange={(e) => setF({ ...f, contact: e.target.value })} /></Field>
    <div className="row wrap" style={{ gap: 16, marginBottom: 10 }}>
      <label className="row"><input type="checkbox" checked={f.catering} onChange={(e) => setF({ ...f, catering: e.target.checked })} /> {t("am.f.catering")}</label>
      {a && a.generator_fee > 0 && <label className="row"><input type="checkbox" checked={f.use_generator} onChange={(e) => setF({ ...f, use_generator: e.target.checked })} /> {t("am.f.generator", { a: money(a.generator_fee) })}</label>}</div>
    {a && a.ext_hour_fee > 0 && <Field label={t("am.f.ext", { a: money(a.ext_hour_fee) })}><select className="input" value={f.ext_hours} onChange={(e) => setF({ ...f, ext_hours: Number(e.target.value) })}>{Array.from({ length: a.max_ext_hours + 1 }).map((_, i) => <option key={i} value={i}>{i}</option>)}</select></Field>}
    <Field label={t("am.f.note")}><input className="input" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
    {q && <Card style={{ background: "var(--surface2)", margin: "8px 0" }}>
      {row(`${t("am.q.rent")} (${t(`am.party.${q.party}`)})${q.free ? ` · ${t("am.q.free")}` : ""}`, q.fee)}{row(t("am.q.ext"), q.ext_fee, q.ext_fee > 0)}{row(t("am.q.cleaning"), q.cleaning, q.cleaning > 0)}{row(t("am.q.generator"), q.generator, q.generator > 0)}{row(t("am.q.deposit"), q.deposit, q.deposit > 0)}
      <div className="row between" style={{ borderTop: "1px solid var(--line)", paddingTop: 6, marginTop: 4 }}><b>{t("am.q.total")}</b><b>{money(q.total)}</b></div>
      <p className="small muted" style={{ margin: "6px 0 0" }}>{t("am.q.note", { n: a?.hold_days ?? 3 })}</p></Card>}
    {err && <p className="error" role="alert">{err}</p>}
    <div className="row"><Btn onClick={go} disabled={busy || !f.on_date || !f.slot || f.contact.trim().length < 6 || f.guests < 1}>{t("am.send")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}

function BookingList({ scope, decide, onChange, toast, amenities }: { scope: "mine" | "all"; decide: boolean; onChange: () => void; toast: ReturnType<typeof useToast>; amenities: Amenity[] }) {
  const { t, pick } = useT(); const { prop, has } = useAuth(); const [data, setData] = useState<Page | null>(null); const [page, setPage] = useState(1); const [q, setQ] = useState(""); const [status, setStatus] = useState(scope === "all" ? "open" : ""); const [am, setAm] = useState(0);
  const [act, setAct] = useState<{ kind: "reject" | "cancel" | "handover" | "refund"; b: Bk } | null>(null); const [err, setErr] = useState("");
  const load = useCallback(() => { const p = new URLSearchParams({ scope, page: String(page), size: String(SIZE) }); if (q) p.set("q", q); if (status) p.set("status", status); if (am) p.set("amenity_id", String(am)); api<Page>(`/amenities/bookings?${p}`).then(setData).catch((e) => setErr(e.message)); }, [scope, page, q, status, am]);
  useEffect(() => { load(); }, [load, prop?.id]);
  const after = () => { setAct(null); load(); onChange(); };
  const approve = async (b: Bk) => { setErr(""); try { await api(`/amenities/bookings/${b.id}/approve`, { method: "POST" }); toast.show(t("am.approved")); after(); } catch (e: any) { setErr(e.message); } };
  return (<>
    <div className="toolbar">
      {scope === "all" && <input className="input" placeholder={t("am.search")} aria-label={t("am.search")} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />}
      <select className="input" aria-label={t("am.f.status")} style={{ maxWidth: 220 }} value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}><option value="">{t("am.all")}</option>{scope === "all" && <option value="open">{t("am.open")}</option>}{Object.keys(TONE).map((s) => <option key={s} value={s}>{t(`am.st.${s}`)}</option>)}</select>
      {amenities.length > 1 && <select className="input" aria-label={t("am.f.amenity")} style={{ maxWidth: 220 }} value={am} onChange={(e) => { setAm(Number(e.target.value)); setPage(1); }}><option value={0}>{t("am.all")}</option>{amenities.map((a) => <option key={a.id} value={a.id}>{pick(a.name, a.name_bn)}</option>)}</select>}
    </div>
    {err && <p className="error" role="alert">{err}</p>}
    {!data ? <p className="muted">{t("common.loading")}</p> : data.items.length === 0 ? <Card><Empty>{t("am.empty")}</Empty></Card> :
      <div className="stack">{data.items.map((b) => (
        <Card key={b.id}>
          <div className="row between wrap" style={{ gap: 12 }}>
            <div style={{ flex: 1, minWidth: 220 }}>
              <div className="row wrap" style={{ gap: 8, marginBottom: 6 }}><Chip tone={TONE[b.status]}>{t(`am.st.${b.status}`)}</Chip><Chip tone="mute">{pick(b.amenity, b.amenity_bn)}</Chip><Chip tone="mute">{t("am.flat", { n: b.unit })}</Chip>{b.conflict && <Chip tone="bad">{t("am.conflict")}</Chip>}</div>
              <h3 style={{ margin: 0 }}>{fdate(b.on_date)} · {t(`am.slot.${b.slot}`)} <span className="small muted">{range(b.hours)}</span></h3>
              <span className="small muted">{t(`am.purpose.${b.purpose}`)} · {t("am.guests", { n: b.guests })}{b.catering ? ` · ${t("am.catering")}` : ""} · {pick(b.by, b.by_bn)}{b.contact ? ` · ${b.contact}` : ""}</span>
              {b.reason && <div className="small" style={{ marginTop: 4 }}>{t("am.reason")}: {b.reason}</div>}
              {b.status === "approved" && b.expires_at && <div className="small" style={{ marginTop: 4, color: "var(--warn)" }}>{t("am.pay_by", { d: fdate(b.expires_at) })}</div>}
              {b.damage_amount > 0 && <div className="small" style={{ marginTop: 4 }}>{t("am.damage")}: {money(b.damage_amount)}{b.damage_note ? ` · ${b.damage_note}` : ""}</div>}
              {b.refund_amount > 0 && <div className="small" style={{ marginTop: 4 }}>{b.refunded_at ? t("am.refunded", { a: money(b.refund_amount), m: t(`bill.m.${b.refund_method}`) }) : t("am.refund_due", { a: money(b.refund_amount) })}</div>}
            </div>
            <div style={{ textAlign: "right" }}>{b.total > 0 && <b>{money(b.total)}</b>}{b.total > 0 && b.invoice_id && b.status === "approved" && <div className="small muted">{t("am.balance", { a: money(b.balance) })}</div>}</div>
          </div>
          <div className="row wrap" style={{ marginTop: 10, gap: 8 }}>
            {b.can_approve && decide && <Btn size="sm" onClick={() => approve(b)}>{t("am.approve")}</Btn>}
            {b.status === "pending" && decide && <Btn size="sm" variant="outline" onClick={() => setAct({ kind: "reject", b })}>{t("am.reject")}</Btn>}
            {b.status === "approved" && b.mine && !has("PROPERTY_ADMIN", "AGENCY_MANAGER") && <Link className="btn btn-primary btn-sm" href="/app/pay">{t("am.pay")}</Link>}
            {b.status === "approved" && b.invoice_id && has("PROPERTY_ADMIN", "AGENCY_MANAGER", "TREASURER") && <Link className="btn btn-soft btn-sm" href="/app/billing">{t("am.take_payment")}</Link>}
            {b.can_permit && <Link className="btn btn-soft btn-sm" href={`/app/amenities/permit/${b.id}`}>{t("am.permit")}</Link>}
            {b.can_handover && <Btn size="sm" variant="soft" onClick={() => setAct({ kind: "handover", b })}>{t("am.handover")}</Btn>}
            {b.can_refund && <Btn size="sm" variant="soft" onClick={() => setAct({ kind: "refund", b })}>{t("am.mark_refund")}</Btn>}
            {b.can_cancel && <Btn size="sm" variant="ghost" onClick={() => setAct({ kind: "cancel", b })}>{t("am.cancel")}</Btn>}
          </div>
        </Card>))}</div>}
    {data && <Pager page={page} size={SIZE} total={data.total} onPage={setPage} />}
    {act && <ActionModal act={act} onClose={() => setAct(null)} onDone={(msg) => { toast.show(msg); after(); }} />}
  </>);
}

function ActionModal({ act, onClose, onDone }: { act: { kind: "reject" | "cancel" | "handover" | "refund"; b: Bk }; onClose: () => void; onDone: (msg: string) => void }) {
  const { t } = useT(); const { kind, b } = act; const [reason, setReason] = useState(""); const [method, setMethod] = useState("cash"); const [dmg, setDmg] = useState("0"); const [note, setNote] = useState(""); const [err, setErr] = useState("");
  const go = async () => {
    try {
      if (kind === "reject") await api(`/amenities/bookings/${b.id}/reject`, { body: { reason } });
      else if (kind === "cancel") await api(`/amenities/bookings/${b.id}/cancel`, { body: { reason } });
      else if (kind === "refund") await api(`/amenities/bookings/${b.id}/refund`, { body: { method } });
      else await api(`/amenities/bookings/${b.id}/handover`, { body: { damage_amount: Math.round(Number(dmg || 0) * 100), damage_note: note, refund_method: method } });
      onDone(t(`am.done.${kind}`));
    } catch (e: any) { setErr(e.message); }
  };
  const back = kind === "handover" ? Math.max(0, b.deposit - Math.round(Number(dmg || 0) * 100)) : b.refund_amount;
  return <Modal title={t(`am.act.${kind}`)} onClose={onClose}>
    <p className="small muted" style={{ marginTop: 0 }}>{fdate(b.on_date)} · {t("am.flat", { n: b.unit })}</p>
    {(kind === "reject" || kind === "cancel") && <Field label={t("am.reason")}><textarea className="input" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>}
    {kind === "cancel" && b.status !== "pending" && <p className="small muted">{t("am.cancel_note")}</p>}
    {kind === "handover" && <>
      <Field label={t("am.damage_amount")} hint={t("am.deposit_held", { a: money(b.deposit) })}><input className="input" type="number" min={0} value={dmg} onChange={(e) => setDmg(e.target.value)} /></Field>
      <Field label={t("am.damage_note")}><input className="input" value={note} onChange={(e) => setNote(e.target.value)} /></Field></>}
    {(kind === "handover" || kind === "refund") && <>
      <p><b>{t("am.give_back", { a: money(back) })}</b></p>
      {back > 0 && <Field label={t("am.refund_method")}><select className="input" value={method} onChange={(e) => setMethod(e.target.value)}>{METHODS.map((m) => <option key={m} value={m}>{t(`bill.m.${m}`)}</option>)}</select></Field>}</>}
    {err && <p className="error" role="alert">{err}</p>}
    <div className="row"><Btn onClick={go} disabled={(kind === "reject" && reason.trim().length < 3)} variant={kind === "cancel" || kind === "reject" ? "danger" : "primary"}>{t(`am.act.${kind}`)}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}

function Settings({ list, onChange, toast }: { list: Amenity[]; onChange: () => void; toast: ReturnType<typeof useToast> }) {
  const { t, pick } = useT(); const [edit, setEdit] = useState<Amenity | "new" | null>(null);
  return (<>
    <div className="row between wrap" style={{ marginBottom: 12 }}><h2 style={{ margin: 0 }}>{t("am.set.amenities")}</h2><Btn size="sm" onClick={() => setEdit("new")}>{t("am.set.add")}</Btn></div>
    <div className="stack">{list.map((a) => (
      <Card key={a.id}><div className="row between wrap" style={{ gap: 10 }}>
        <div><div className="row wrap" style={{ gap: 8 }}><h3 style={{ margin: 0 }}>{pick(a.name, a.name_bn)}</h3><Chip tone="mute">{t(`am.kind.${a.kind}`)}</Chip>{!a.active && <Chip tone="bad">{t("am.inactive")}</Chip>}</div>
          <span className="small muted">{t("am.cap", { n: a.capacity })} · {SLOTS.filter((s) => a.slots[s]?.on).map((s) => `${t(`am.slot.${s}`)} ${money(a.slots[s].owner)} / ${money(a.slots[s].tenant)}`).join(" · ")}</span>
          <div className="small muted">{t("am.deposit")} {money(a.deposit)} · {t("am.q.cleaning")} {money(a.cleaning_fee)}</div></div>
        <Btn size="sm" variant="soft" onClick={() => setEdit(a)}>{t("common.edit")}</Btn></div></Card>))}</div>
    <Blackouts list={list} toast={toast} />
    {edit && <AmenityEditor a={edit === "new" ? null : edit} onClose={() => setEdit(null)} onDone={() => { setEdit(null); toast.show(t("am.saved")); onChange(); }} />}
  </>);
}

function Blackouts({ list, toast }: { list: Amenity[]; toast: ReturnType<typeof useToast> }) {
  const { t, pick, lang } = useT(); const [data, setData] = useState<{ items: Blk[]; total: number } | null>(null); const [page, setPage] = useState(1); const [f, setF] = useState({ on_date: "", amenity_id: 0, reason: "" }); const [err, setErr] = useState("");
  const load = useCallback(() => { api<{ items: Blk[]; total: number }>(`/amenities/blackouts?page=${page}&size=${SIZE}`).then(setData); }, [page]);
  useEffect(() => { load(); }, [load]);
  const add = async () => { setErr(""); try { const r = await api<{ affected: number }>("/amenities/blackouts", { body: { on_date: f.on_date, amenity_id: f.amenity_id || null, ...(lang === "bn" ? { reason_bn: f.reason } : { reason: f.reason }) } }); toast.show(r.affected ? t("am.blk.affected", { n: r.affected }) : t("am.saved")); setF({ on_date: "", amenity_id: 0, reason: "" }); load(); } catch (e: any) { setErr(e.message); } };
  return (<div style={{ marginTop: 22 }}>
    <h2>{t("am.blk.title")}</h2><p className="muted" style={{ marginTop: 0 }}>{t("am.blk.sub")}</p>
    <Card><div className="grid g3">
      <Field label={t("am.f.date")}><input className="input" type="date" value={f.on_date} onChange={(e) => setF({ ...f, on_date: e.target.value })} /></Field>
      <Field label={t("am.f.amenity")}><select className="input" value={f.amenity_id} onChange={(e) => setF({ ...f, amenity_id: Number(e.target.value) })}><option value={0}>{t("am.blk.all")}</option>{list.map((a) => <option key={a.id} value={a.id}>{pick(a.name, a.name_bn)}</option>)}</select></Field>
      <Field label={t("am.blk.reason")}><input className="input" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></Field></div>
      {err && <p className="error" role="alert">{err}</p>}<Btn size="sm" disabled={!f.on_date} onClick={add}>{t("am.blk.add")}</Btn></Card>
    {data && (data.items.length === 0 ? <p className="muted">{t("am.blk.none")}</p> : <div className="stack" style={{ marginTop: 12 }}>{data.items.map((b) => (
      <Card key={b.id}><div className="row between wrap"><div><b>{fdate(b.on_date)}</b> <span className="small muted">· {b.amenity_id ? pick(list.find((a) => a.id === b.amenity_id)?.name, list.find((a) => a.id === b.amenity_id)?.name_bn) : t("am.blk.all")} · {pick(b.reason, b.reason_bn)}</span></div>
        <Btn size="sm" variant="ghost" onClick={async () => { await api(`/amenities/blackouts/${b.id}`, { method: "DELETE" }); load(); }}>{t("am.blk.remove")}</Btn></div></Card>))}</div>)}
    {data && <Pager page={page} size={SIZE} total={data.total} onPage={setPage} />}
  </div>);
}

const taka = (p: number) => String(p / 100);
const paisa = (s: string) => Math.max(0, Math.round(Number(s || 0) * 100));

function AmenityEditor({ a, onClose, onDone }: { a: Amenity | null; onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [lt, setLt] = useState<"en" | "bn">("en"); const [err, setErr] = useState("");
  const [f, setF] = useState({ kind: a?.kind ?? "hall", name: a?.name ?? "", name_bn: a?.name_bn ?? "", capacity: String(a?.capacity ?? 100), rules: a?.rules ?? "", rules_bn: a?.rules_bn ?? "", photo_url: a?.photo_url ?? "", active: a?.active ?? true,
    ext_hour_fee: taka(a?.ext_hour_fee ?? 0), max_ext_hours: String(a?.max_ext_hours ?? 2), deposit: taka(a?.deposit ?? 0), cleaning_fee: taka(a?.cleaning_fee ?? 0), generator_fee: taka(a?.generator_fee ?? 0), free_quota: String(a?.free_quota ?? 0),
    min_notice_days: String(a?.min_notice_days ?? 3), max_advance_days: String(a?.max_advance_days ?? 90), hold_days: String(a?.hold_days ?? 3) });
  const [slots, setSlots] = useState<Record<string, { on: boolean; owner: string; tenant: string }>>(Object.fromEntries(SLOTS.map((s) => [s, { on: a?.slots[s]?.on ?? false, owner: taka(a?.slots[s]?.owner ?? 0), tenant: taka(a?.slots[s]?.tenant ?? 0) }])));
  const [rules, setRules] = useState<Rule[]>(a?.cancel_rules?.length ? a.cancel_rules : [{ days: 14, pct: 100 }, { days: 7, pct: 50 }, { days: 0, pct: 0 }]);
  const set = (k: string, v: string | boolean) => setF({ ...f, [k]: v });
  const num = (k: keyof typeof f, label: string, money = false) => <Field label={label}><input className="input" type="number" min={0} value={String(f[k])} onChange={(e) => set(k, e.target.value)} />{money && null}</Field>;
  const save = async () => {
    const body = { kind: f.kind, name: f.name, name_bn: f.name_bn, capacity: Number(f.capacity), rules: f.rules, rules_bn: f.rules_bn, photo_url: f.photo_url, active: f.active,
      slots: Object.fromEntries(SLOTS.map((s) => [s, { on: slots[s].on, owner: paisa(slots[s].owner), tenant: paisa(slots[s].tenant) }])),
      ext_hour_fee: paisa(f.ext_hour_fee), max_ext_hours: Number(f.max_ext_hours), deposit: paisa(f.deposit), cleaning_fee: paisa(f.cleaning_fee), generator_fee: paisa(f.generator_fee), free_quota: Number(f.free_quota),
      min_notice_days: Number(f.min_notice_days), max_advance_days: Number(f.max_advance_days), hold_days: Number(f.hold_days), cancel_rules: rules };
    try { await api(a ? `/amenities/${a.id}` : "/amenities", { method: a ? "PUT" : "POST", body }); onDone(); } catch (e: any) { setErr(e.message); }
  };
  return <Modal title={a ? t("am.set.edit") : t("am.set.add")} onClose={onClose}>
    <Tabs value={lt} onChange={setLt} items={[{ id: "en", label: "English" }, { id: "bn", label: "বাংলা" }]} />
    <div style={{ marginTop: 12 }}>{lt === "en" ? <>
      <Field label={t("am.set.name")}><input className="input" value={f.name} onChange={(e) => set("name", e.target.value)} /></Field>
      <Field label={t("am.rules")}><textarea className="input" rows={3} value={f.rules} onChange={(e) => set("rules", e.target.value)} /></Field></> : <>
      <Field label={t("am.set.name")}><input className="input" value={f.name_bn} onChange={(e) => set("name_bn", e.target.value)} /></Field>
      <Field label={t("am.rules")}><textarea className="input" rows={3} value={f.rules_bn} onChange={(e) => set("rules_bn", e.target.value)} /></Field></>}</div>
    <div className="grid g2">
      <Field label={t("am.set.kind")}><select className="input" value={f.kind} onChange={(e) => set("kind", e.target.value)}>{KINDS.map((k) => <option key={k} value={k}>{t(`am.kind.${k}`)}</option>)}</select></Field>
      {num("capacity", t("am.set.capacity"))}</div>
    <label className="row" style={{ marginBottom: 12 }}><input type="checkbox" checked={f.active} onChange={(e) => set("active", e.target.checked)} /> {t("am.set.active")}</label>
    <h3 style={{ marginBottom: 6 }}>{t("am.set.prices")}</h3><p className="small muted" style={{ marginTop: 0 }}>{t("am.set.prices_hint")}</p>
    {SLOTS.map((s) => <div key={s} className="row wrap" style={{ gap: 8, padding: "6px 0", borderTop: "1px solid var(--line)" }}>
      <label className="row" style={{ minWidth: 120 }}><input type="checkbox" checked={slots[s].on} onChange={(e) => setSlots({ ...slots, [s]: { ...slots[s], on: e.target.checked } })} /> {t(`am.slot.${s}`)}</label>
      <input className="input" type="number" min={0} style={{ width: 110 }} aria-label={`${t(`am.slot.${s}`)} ${t("am.party.owner")}`} placeholder={t("am.party.owner")} disabled={!slots[s].on} value={slots[s].owner} onChange={(e) => setSlots({ ...slots, [s]: { ...slots[s], owner: e.target.value } })} />
      <input className="input" type="number" min={0} style={{ width: 110 }} aria-label={`${t(`am.slot.${s}`)} ${t("am.party.tenant")}`} placeholder={t("am.party.tenant")} disabled={!slots[s].on} value={slots[s].tenant} onChange={(e) => setSlots({ ...slots, [s]: { ...slots[s], tenant: e.target.value } })} /></div>)}
    <div className="grid g2" style={{ marginTop: 10 }}>
      {num("deposit", t("am.deposit"))}{num("cleaning_fee", t("am.q.cleaning"))}{num("generator_fee", t("am.set.generator"))}{num("ext_hour_fee", t("am.set.ext"))}{num("max_ext_hours", t("am.set.max_ext"))}{num("free_quota", t("am.set.free"))}</div>
    <h3 style={{ marginBottom: 6 }}>{t("am.set.rules")}</h3>
    <div className="grid g3">{num("min_notice_days", t("am.set.min_notice"))}{num("max_advance_days", t("am.set.max_adv"))}{num("hold_days", t("am.set.hold"))}</div>
    <h3 style={{ marginBottom: 6 }}>{t("am.set.cancel")}</h3><p className="small muted" style={{ marginTop: 0 }}>{t("am.set.cancel_hint")}</p>
    {rules.map((r, i) => <div key={i} className="row" style={{ gap: 8, marginBottom: 6 }}>
      <input className="input" type="number" min={0} style={{ width: 90 }} aria-label={t("am.set.days")} value={r.days} onChange={(e) => setRules(rules.map((x, j) => j === i ? { ...x, days: Number(e.target.value) } : x))} /><span className="small">{t("am.set.days")}</span>
      <input className="input" type="number" min={0} max={100} style={{ width: 90 }} aria-label={t("am.set.pct")} value={r.pct} onChange={(e) => setRules(rules.map((x, j) => j === i ? { ...x, pct: Number(e.target.value) } : x))} /><span className="small">%</span>
      <Btn size="sm" variant="ghost" onClick={() => setRules(rules.filter((_, j) => j !== i))} aria-label={t("am.blk.remove")}>✕</Btn></div>)}
    <Btn size="sm" variant="soft" onClick={() => setRules([...rules, { days: 0, pct: 0 }])}>{t("am.set.rule_add")}</Btn>
    {err && <p className="error" role="alert">{err}</p>}
    <div className="row" style={{ marginTop: 14 }}><Btn onClick={save} disabled={f.name.trim().length < 2}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div></Modal>;
}
