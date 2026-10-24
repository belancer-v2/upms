"use client";
import { useCallback, useEffect, useState } from "react";
import { Btn, Card, Chip, Empty, Field, Modal, PageHead, Stat, Tabs, useToast } from "@/components/ui";
import { Pager } from "@/components/pager";
import { api, fdate, ftime, store } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

const KINDS = ["car", "motorbike", "bicycle"];
const STATES = ["free", "occupied", "visitor", "blocked"];
const TILE: Record<string, { bg: string; fg: string; ring?: string }> = {
  free: { bg: "var(--ok-bg)", fg: "var(--ok)" }, occupied: { bg: "var(--blush)", fg: "var(--blush-text)" },
  visitor: { bg: "var(--info-bg)", fg: "var(--info)" }, blocked: { bg: "var(--surface2)", fg: "var(--muted)", ring: "var(--line)" },
};

type Slot = { id: number; code: string; level: string; kind: string; cover: string; status: string; visitor: boolean; note: string; state: string; unit_id: number | null; unit: string; owner: string; owner_bn: string; in_use: boolean; since?: string };
type Veh = { id: number; unit_id: number; unit: string; reg_no: string; kind: string; make_model: string; colour: string; sticker: string; holder_kind: string; temporary: boolean; status: string; has_photo: boolean };
type Paged<T> = { items: T[]; total: number; page: number; size: number };
type Sum = { slots: number; occupied: number; free: number; visitor: number; blocked: number; flats_unmet: number; vehicles: number; to_review: number; page_size: number };
type Mine = { unit: { id: number; number: string }; entitlement: Record<string, number>; held: Record<string, number>; slots: Slot[]; vehicles: Veh[]; allowed: number; used: number; temp_used: number };
type Unmet = { unit_id: number; unit: string; missing: Record<string, number> };

async function upload(path: string, file: File) {
  const fd = new FormData(); fd.append("file", file);
  const h: Record<string, string> = {}; if (store.token) h.Authorization = `Bearer ${store.token}`; if (store.prop) h["X-Property-Id"] = String(store.prop);
  const r = await fetch(`/api${path}`, { method: "POST", headers: h, body: fd });
  if (!r.ok) { let m = r.statusText; try { const j = await r.json(); m = typeof j.detail === "string" ? j.detail : m; } catch {} throw new Error(m); }
}

function Photo({ v }: { v: Veh }) {
  const { t } = useT(); const [src, setSrc] = useState("");
  useEffect(() => {
    if (!v.has_photo) { setSrc(""); return; }
    let url = ""; const h: Record<string, string> = {}; if (store.token) h.Authorization = `Bearer ${store.token}`; if (store.prop) h["X-Property-Id"] = String(store.prop);
    fetch(`/api/parking/vehicles/${v.id}/photo`, { headers: h }).then((r) => (r.ok ? r.blob() : null)).then((b) => { if (b) { url = URL.createObjectURL(b); setSrc(url); } });
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [v.id, v.has_photo]);
  return src ? <img src={src} alt={`${t("pk.photo")} ${v.reg_no}`} style={{ width: 64, height: 48, objectFit: "cover", borderRadius: 10 }} /> : <div className="small muted" style={{ width: 64, height: 48, borderRadius: 10, background: "var(--surface2)", display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center", fontSize: 11 }}>{t("pk.photo_none")}</div>;
}

function VehicleForm({ unit, kinds, admin, onClose, onDone }: { unit: number; kinds: string[]; admin: boolean; onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [f, setF] = useState({ reg_no: "", kind: kinds[0] ?? "car", make_model: "", colour: "", sticker: "", temporary: false }); const [file, setFile] = useState<File | null>(null); const [err, setErr] = useState("");
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value });
  const save = async () => {
    try { const v = await api("/parking/vehicles", { body: { ...f, unit_id: unit } }); if (file) await upload(`/parking/vehicles/${v.id}/photo`, file); onDone(); } catch (e: any) { setErr(e.message); }
  };
  return (
    <Modal title={t("pk.veh_add")} onClose={onClose}>
      <Field label={t("pk.f.reg")} hint={t("pk.f.reg_hint")}><input className="input" value={f.reg_no} onChange={set("reg_no")} /></Field>
      <div className="grid g2"><Field label={t("pk.f.kind")}><select className="input" value={f.kind} onChange={set("kind")}>{(admin && f.temporary ? KINDS : kinds).map((k) => <option key={k} value={k}>{t(`pk.kind.${k}`)}</option>)}</select></Field>
        <Field label={t("pk.f.sticker")}><input className="input" value={f.sticker} onChange={set("sticker")} /></Field>
        <Field label={t("pk.f.make")}><input className="input" value={f.make_model} onChange={set("make_model")} /></Field><Field label={t("pk.f.colour")}><input className="input" value={f.colour} onChange={set("colour")} /></Field></div>
      <Field label={t("pk.f.photo")}><input className="input" type="file" accept="image/jpeg,image/png" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
      {admin && <label className="row" style={{ marginBottom: 12 }}><input type="checkbox" checked={f.temporary} onChange={set("temporary")} /> {t("pk.f.temp")}</label>}
      {err && <p className="error" role="alert">{err}</p>}
      <div className="row"><Btn onClick={save} disabled={f.reg_no.trim().length < 3}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div>
    </Modal>
  );
}

function VehicleRow({ v, canEdit, onChange, showUnit }: { v: Veh; canEdit: boolean; onChange: () => void; showUnit?: boolean }) {
  const { t } = useT(); const [err, setErr] = useState("");
  const act = async (fn: () => Promise<unknown>) => { try { await fn(); onChange(); } catch (e: any) { setErr(e.message); } };
  return (
    <div className="row between wrap" style={{ padding: "10px 0", borderTop: "1px solid var(--line)", gap: 12 }}>
      <div className="row" style={{ gap: 12 }}><Photo v={v} />
        <div><b>{v.reg_no}</b> {showUnit && <span className="small muted">· {t("pk.flat", { n: v.unit })}</span>}<div className="row wrap" style={{ gap: 6, marginTop: 4 }}>
          <Chip tone="mute">{t(`pk.kind.${v.kind}`)}</Chip>{v.temporary && <Chip tone="info">{t("pk.veh_temp")}</Chip>}{v.status === "to_review" && <Chip tone="warn">{t("pk.veh_review")}</Chip>}{v.holder_kind === "tenant" && <Chip tone="mute">{t("pk.veh_tenant")}</Chip>}</div>
          <span className="small muted">{[v.make_model, v.colour, v.sticker].filter(Boolean).join(" · ")}</span>{err && <p className="error" role="alert">{err}</p>}</div></div>
      {canEdit && <div className="row wrap">
        {v.status === "to_review" && <Btn size="sm" variant="soft" onClick={() => act(() => api(`/parking/vehicles/${v.id}/keep`, { method: "POST" }))}>{t("pk.veh_keep")}</Btn>}
        <label className="btn btn-ghost btn-sm" style={{ cursor: "pointer" }}>{t("pk.photo_add")}<input type="file" accept="image/jpeg,image/png" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) act(() => upload(`/parking/vehicles/${v.id}/photo`, f)); }} /></label>
        <Btn size="sm" variant="ghost" onClick={() => confirm(t("pk.veh_confirm_rm")) && act(() => api(`/parking/vehicles/${v.id}`, { method: "DELETE" }))}>{t("pk.veh_remove")}</Btn></div>}
    </div>
  );
}

function MyParking() {
  const { t } = useT(); const { prop, has } = useAuth(); const toast = useToast(); const admin = has("PROPERTY_ADMIN", "AGENCY_MANAGER");
  const [data, setData] = useState<Mine[] | null>(null); const [add, setAdd] = useState<Mine | null>(null);
  const load = useCallback(() => { api<Mine[]>("/parking/mine").then(setData).catch(() => setData([])); }, []);
  useEffect(() => { load(); }, [load, prop?.id]);
  if (!data) return <p className="muted">{t("common.loading")}</p>;
  if (!data.length) return <Card><Empty>{t("pk.no_slots")}</Empty></Card>;
  return (<div className="stack">{data.map((m) => (
    <Card key={m.unit.id}>
      <div className="row between wrap" style={{ gap: 8 }}><h3 style={{ margin: 0 }}>{t("pk.flat", { n: m.unit.number })}</h3>
        <span className="small muted">{KINDS.filter((k) => m.entitlement[k]).map((k) => t("pk.ent_line", { k: t(`pk.kind.${k}`), h: m.held[k], e: m.entitlement[k] })).join(" · ")}</span></div>
      <h4 style={{ margin: "14px 0 6px" }}>{t("pk.slots")}</h4>
      {m.slots.length ? <div className="row wrap" style={{ gap: 10 }}>{m.slots.map((s) => (
        <div key={s.id} style={{ background: TILE.occupied.bg, color: TILE.occupied.fg, borderRadius: 14, padding: "10px 14px", minWidth: 140 }}><b>{s.code}</b><br /><span className="small">{t(`pk.kind.${s.kind}`)} · {t(`pk.cover.${s.cover}`)}{s.level ? ` · ${s.level}` : ""}</span>{s.since && <><br /><span className="small">{t("pk.since", { d: fdate(s.since) })}</span></>}</div>))}</div> : <p className="muted small">{t("pk.no_slots")}</p>}
      <div className="row between" style={{ margin: "18px 0 4px" }}><h4 style={{ margin: 0 }}>{t("pk.veh")} <span className="small muted">· {t("pk.veh_limit", { u: m.used, a: m.allowed })}</span></h4>
        {(m.slots.length > 0 || admin) && <Btn size="sm" onClick={() => setAdd(m)}>{t("pk.veh_add")}</Btn>}</div>
      {m.vehicles.some((v) => v.status === "to_review") && <p className="small" style={{ background: "var(--warn-bg)", color: "var(--warn)", padding: 10, borderRadius: 12, fontWeight: 700 }}>{t("pk.veh_review_note")}</p>}
      {m.vehicles.length ? m.vehicles.map((v) => <VehicleRow key={v.id} v={v} canEdit onChange={load} />) : <p className="muted small">{t("pk.veh_none")}</p>}
    </Card>))}
    {add && <VehicleForm unit={add.unit.id} kinds={KINDS.filter((k) => add.held[k] > 0)} admin={admin} onClose={() => setAdd(null)} onDone={() => { setAdd(null); toast.show(t("pk.veh_saved")); load(); }} />}
    {toast.node}</div>);
}

function SlotModal({ slot, manage, onClose, onChange }: { slot: Slot; manage: boolean; onClose: () => void; onChange: (msg?: string) => void }) {
  const { t, pick } = useT(); const [flat, setFlat] = useState(""); const [other, setOther] = useState(""); const [err, setErr] = useState("");
  const run = async (fn: () => Promise<unknown>) => { try { setErr(""); await fn(); onChange(t("pk.done")); } catch (e: any) { setErr(e.message); } };
  const give = () => run(async () => {
    const us = await api<{ id: number; number: string }[]>("/units"); const u = us.find((x) => x.number.toLowerCase() === flat.trim().toLowerCase());
    if (!u) throw new Error(t("pk.bad_flat")); await api(`/parking/slots/${slot.id}/allocate`, { body: { unit_id: u.id } });
  });
  const swap = () => run(async () => {
    const r = await api<Paged<Slot>>(`/parking/slots?q=${encodeURIComponent(other.trim())}&size=100`); const o = r.items.find((x) => x.code.toLowerCase() === other.trim().toLowerCase());
    if (!o) throw new Error(t("pk.bad_slot")); await api("/parking/swap", { body: { slot_a: slot.id, slot_b: o.id } });
  });
  return (
    <Modal title={t("pk.slot", { c: slot.code })} onClose={onClose}>
      <div className="row wrap" style={{ marginBottom: 12 }}><Chip tone={slot.state === "free" ? "ok" : slot.state === "blocked" ? "mute" : slot.state === "visitor" ? "info" : ""}>{t(`pk.state.${slot.state}`)}</Chip><Chip tone="mute">{t(`pk.kind.${slot.kind}`)}</Chip><Chip tone="mute">{t(`pk.cover.${slot.cover}`)}</Chip>{slot.level && <Chip tone="mute">{slot.level}</Chip>}</div>
      {slot.unit ? <p><b>{t("pk.held_by", { n: slot.unit })}</b><br /><span className="small muted">{t("pk.owner", { n: pick(slot.owner, slot.owner_bn) })}</span></p> : slot.state === "free" ? <p className="muted">{t("pk.free_note")}</p> : null}
      {slot.in_use && <p className="small" style={{ color: "var(--info)", fontWeight: 700 }}>{t("pk.in_use")}</p>}
      {slot.note && <p className="small muted">{slot.note}</p>}
      {manage && !slot.visitor && slot.status === "active" && <>
        <Field label={slot.unit ? t("pk.move") : t("pk.give")}><div className="row"><input className="input" placeholder={t("pk.pick_flat")} value={flat} onChange={(e) => setFlat(e.target.value)} /><Btn onClick={give} disabled={!flat.trim()}>{t("common.save")}</Btn></div></Field>
        {slot.unit && <Field label={t("pk.swap")}><div className="row"><input className="input" placeholder={t("pk.swap_with")} value={other} onChange={(e) => setOther(e.target.value)} /><Btn variant="soft" onClick={swap} disabled={!other.trim()}>{t("pk.swap_do")}</Btn></div></Field>}
      </>}
      {err && <p className="error" role="alert">{err}</p>}
      {manage && <div className="row wrap" style={{ marginTop: 10 }}>
        {slot.unit && <Btn variant="ghost" onClick={() => confirm(t("pk.confirm_back")) && run(() => api(`/parking/slots/${slot.id}/unallocate`, { method: "POST" }))}>{t("pk.take_back")}</Btn>}
        {!slot.unit && <Btn variant="ghost" onClick={() => run(() => api(`/parking/slots/${slot.id}`, { method: "PUT", body: { status: slot.status === "blocked" ? "active" : "blocked" } }))}>{slot.status === "blocked" ? t("pk.unblock") : t("pk.block")}</Btn>}</div>}
    </Modal>
  );
}

function SlotForm({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { t } = useT(); const [f, setF] = useState({ code: "", level: "", kind: "car", cover: "open", visitor: false, note: "" }); const [err, setErr] = useState("");
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value });
  const save = async () => { try { await api("/parking/slots", { body: f }); onDone(); } catch (e: any) { setErr(e.message); } };
  return (
    <Modal title={t("pk.add")} onClose={onClose}>
      <div className="grid g2"><Field label={t("pk.f.code")} hint={t("pk.f.code_hint")}><input className="input" value={f.code} onChange={set("code")} /></Field><Field label={t("pk.f.level")}><input className="input" value={f.level} onChange={set("level")} /></Field>
        <Field label={t("pk.f.kind")}><select className="input" value={f.kind} onChange={set("kind")}>{KINDS.map((k) => <option key={k} value={k}>{t(`pk.kind.${k}`)}</option>)}</select></Field>
        <Field label={t("pk.f.cover")}><select className="input" value={f.cover} onChange={set("cover")}>{["open", "covered"].map((k) => <option key={k} value={k}>{t(`pk.cover.${k}`)}</option>)}</select></Field></div>
      <Field label={t("pk.f.note")}><input className="input" value={f.note} onChange={set("note")} /></Field>
      <label className="row" style={{ marginBottom: 12 }}><input type="checkbox" checked={f.visitor} onChange={set("visitor")} /> {t("pk.f.visitor")}</label>
      {err && <p className="error" role="alert">{err}</p>}
      <div className="row"><Btn onClick={save} disabled={!f.code.trim()}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div>
    </Modal>
  );
}

function SlotMap({ manage, onChanged }: { manage: boolean; onChanged: () => void }) {
  const { t } = useT(); const { prop } = useAuth(); const toast = useToast();
  const [data, setData] = useState<Paged<Slot> | null>(null); const [page, setPage] = useState(1); const [q, setQ] = useState(""); const [state, setState] = useState(""); const [kind, setKind] = useState("");
  const [open, setOpen] = useState<Slot | null>(null); const [form, setForm] = useState(false);
  const load = useCallback(() => { const p = new URLSearchParams({ page: String(page) }); if (q) p.set("q", q); if (state) p.set("state", state); if (kind) p.set("kind", kind); api<Paged<Slot>>(`/parking/slots?${p}`).then(setData); }, [page, q, state, kind]);
  useEffect(() => { load(); }, [load, prop?.id]);
  return (<>
    <div className="toolbar">
      <input className="input" placeholder={t("pk.search")} aria-label={t("pk.search")} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
      <select className="input" aria-label={t("pk.f.state")} style={{ maxWidth: 170 }} value={state} onChange={(e) => { setState(e.target.value); setPage(1); }}><option value="">{t("pk.all")}</option>{STATES.map((s) => <option key={s} value={s}>{t(`pk.state.${s}`)}</option>)}</select>
      <select className="input" aria-label={t("pk.f.kind")} style={{ maxWidth: 170 }} value={kind} onChange={(e) => { setKind(e.target.value); setPage(1); }}><option value="">{t("pk.all")}</option>{KINDS.map((k) => <option key={k} value={k}>{t(`pk.kind.${k}`)}</option>)}</select>
      {manage && <Btn onClick={() => setForm(true)}>{t("pk.add")}</Btn>}
    </div>
    <div className="row wrap small" style={{ gap: 14, marginBottom: 12 }}>{STATES.map((s) => <span key={s} className="row" style={{ gap: 6 }}><i style={{ width: 14, height: 14, borderRadius: 5, background: TILE[s].bg, border: `2px solid ${TILE[s].ring ?? TILE[s].fg}`, display: "inline-block" }} />{t(`pk.state.${s}`)}</span>)}</div>
    {!data ? <p className="muted">{t("common.loading")}</p> : data.items.length === 0 ? <Card><Empty>{t("pk.empty")}</Empty></Card> :
      <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fill, minmax(124px, 1fr))" }}>{data.items.map((s) => { const c = TILE[s.state]; return (
        <button key={s.id} onClick={() => setOpen(s)} aria-label={`${s.code} ${t(`pk.state.${s.state}`)} ${s.unit}`} style={{ background: c.bg, color: c.fg, border: `2px solid ${c.ring ?? "transparent"}`, borderRadius: 14, padding: "10px 8px", font: "inherit", cursor: "pointer", textAlign: "center" }}>
          <b style={{ fontSize: 14 }}>{s.code}</b><br /><span className="small">{s.unit ? t("pk.flat", { n: s.unit }) : t(`pk.state.${s.state}`)}</span><br /><span style={{ fontSize: 11 }}>{t(`pk.kind.${s.kind}`)}{s.in_use ? " ●" : ""}</span></button>); })}</div>}
    {data && <Pager page={page} size={data.size} total={data.total} onPage={setPage} />}
    {open && <SlotModal slot={open} manage={manage} onClose={() => setOpen(null)} onChange={(m) => { setOpen(null); if (m) toast.show(m); load(); onChanged(); }} />}
    {form && <SlotForm onClose={() => setForm(false)} onDone={() => { setForm(false); toast.show(t("pk.done")); load(); onChanged(); }} />}
    {toast.node}
  </>);
}

function Handover() {
  const { t } = useT(); const { prop } = useAuth(); const [which, setWhich] = useState<"free" | "unmet">("unmet"); const [page, setPage] = useState(1); const [q, setQ] = useState("");
  const [data, setData] = useState<Paged<any> | null>(null);
  useEffect(() => { api<Paged<any>>(`/parking/handover?which=${which}&page=${page}&q=${encodeURIComponent(q)}`).then(setData); }, [which, page, q, prop?.id]);
  return (<>
    <div className="toolbar"><Tabs value={which} onChange={(v) => { setWhich(v); setPage(1); }} items={[{ id: "unmet", label: t("pk.ho.unmet") }, { id: "free", label: t("pk.ho.free") }]} />
      <input className="input" placeholder={t("pk.ho.search")} aria-label={t("pk.ho.search")} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} /></div>
    {!data ? <p className="muted">{t("common.loading")}</p> : data.items.length === 0 ? <Card><Empty>{t("pk.ho.empty")}</Empty></Card> :
      <div className="stack">{data.items.map((r: any) => which === "free" ? (
        <Card key={r.id}><div className="row between"><div><b>{r.code}</b> <span className="small muted">{r.level}</span></div><div className="row"><Chip tone="mute">{t(`pk.kind.${r.kind}`)}</Chip><Chip tone="mute">{t(`pk.cover.${r.cover}`)}</Chip></div></div></Card>) : (
        <Card key={r.unit_id}><div className="row between wrap"><b>{t("pk.flat", { n: r.unit })}</b><div className="row wrap">{Object.entries(r.missing as Record<string, number>).map(([k, n]) => <Chip key={k} tone="warn">{t("pk.ho.missing", { n, k: t(`pk.kind.${k}`).toLowerCase() })}</Chip>)}</div></div></Card>))}</div>}
    {data && <Pager page={page} size={data.size} total={data.total} onPage={setPage} />}
  </>);
}

function Vehicles() {
  const { t } = useT(); const { prop, has } = useAuth(); const manage = has("PROPERTY_ADMIN", "AGENCY_MANAGER");
  const [data, setData] = useState<Paged<Veh> | null>(null); const [page, setPage] = useState(1); const [q, setQ] = useState(""); const [st, setSt] = useState("");
  const load = useCallback(() => { api<Paged<Veh>>(`/parking/vehicles?page=${page}&q=${encodeURIComponent(q)}&status=${st}`).then(setData); }, [page, q, st]);
  useEffect(() => { load(); }, [load, prop?.id]);
  return (<>
    <div className="toolbar"><input className="input" placeholder={t("pk.veh_search")} aria-label={t("pk.veh_search")} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
      <select className="input" aria-label={t("pk.f.state")} style={{ maxWidth: 190 }} value={st} onChange={(e) => { setSt(e.target.value); setPage(1); }}><option value="">{t("pk.all")}</option><option value="to_review">{t("pk.veh_review")}</option></select></div>
    {!data ? <p className="muted">{t("common.loading")}</p> : data.items.length === 0 ? <Card><Empty>{t("pk.veh_none")}</Empty></Card> : <Card>{data.items.map((v) => <VehicleRow key={v.id} v={v} canEdit={manage} showUnit onChange={load} />)}</Card>}
    {data && <Pager page={page} size={data.size} total={data.total} onPage={setPage} />}
  </>);
}

type Hit = { reg_no: string; kind: string; make_model: string; colour: string; sticker: string; status: string; temporary: boolean; unit: string; owner: string; owner_bn: string; slots: string[] };
type Visit = { id: number; plate: string; slot: string; slot_id: number; in_at: string; out_at: string | null };
type VisitList = Paged<Visit> & { bays: { id: number; code: string; kind: string; busy: boolean }[] };

function Gate() {
  const { t, pick } = useT(); const { prop } = useAuth(); const toast = useToast();
  const [reg, setReg] = useState(""); const [hits, setHits] = useState<Hit[] | null>(null); const [err, setErr] = useState("");
  const [plate, setPlate] = useState(""); const [bay, setBay] = useState(""); const [vis, setVis] = useState<VisitList | null>(null); const [page, setPage] = useState(1); const [openOnly, setOpenOnly] = useState(false);
  const check = async () => { try { setErr(""); setHits((await api<{ items: Hit[] }>(`/parking/lookup?reg=${encodeURIComponent(reg)}`)).items); } catch (e: any) { setErr(e.message); } };
  const load = useCallback(() => { api<VisitList>(`/parking/visits?page=${page}&open_only=${openOnly}`).then(setVis); }, [page, openOnly]);
  useEffect(() => { load(); }, [load, prop?.id]);
  const free = vis?.bays.filter((b) => !b.busy) ?? [];
  const logIn = async () => { try { setErr(""); await api("/parking/visits", { body: { plate, slot_id: Number(bay || free[0]?.id) } }); setPlate(""); toast.show(t("pk.vis.saved")); load(); } catch (e: any) { setErr(e.message); } };
  const out = async (id: number) => { try { await api(`/parking/visits/${id}/out`, { method: "POST" }); load(); } catch (e: any) { setErr(e.message); } };
  return (<div className="grid g2" style={{ alignItems: "start" }}>
    <Card><h3 style={{ marginTop: 0 }}>{t("pk.gate.title")}</h3>
      <div className="row"><input className="input" placeholder={t("pk.gate.ph")} aria-label={t("pk.gate.ph")} value={reg} onChange={(e) => setReg(e.target.value)} onKeyDown={(e) => e.key === "Enter" && reg.trim().length >= 2 && check()} /><Btn onClick={check} disabled={reg.trim().length < 2}>{t("pk.gate.go")}</Btn></div>
      {hits && (hits.length === 0 ? <p className="muted" style={{ marginTop: 12 }}>{t("pk.gate.none")}</p> : hits.map((h) => (
        <div key={h.reg_no} style={{ borderTop: "1px solid var(--line)", marginTop: 12, paddingTop: 10 }}>
          <b>{h.reg_no}</b> <span className="small muted">{[h.make_model, h.colour].filter(Boolean).join(" · ")}</span>
          <div className="row wrap" style={{ gap: 6, margin: "6px 0" }}><Chip tone="ok">{t("pk.flat", { n: h.unit })}</Chip>{h.slots.map((s) => <Chip key={s} tone="mute">{t("pk.gate.slot", { s })}</Chip>)}<Chip tone="mute">{t(`pk.kind.${h.kind}`)}</Chip>{h.status === "to_review" && <Chip tone="warn">{t("pk.veh_review")}</Chip>}{h.temporary && <Chip tone="info">{t("pk.veh_temp")}</Chip>}</div>
          <span className="small">{t("pk.gate.owner", { n: pick(h.owner, h.owner_bn) })}</span></div>)))}
    </Card>
    <Card><h3 style={{ marginTop: 0 }}>{t("pk.vis.title")}</h3>
      <div className="row wrap" style={{ marginBottom: 10 }}>{vis?.bays.map((b) => <Chip key={b.id} tone={b.busy ? "warn" : "ok"}>{b.code} · {b.busy ? t("pk.vis.busy") : t("pk.vis.free")}</Chip>)}</div>
      {free.length === 0 ? <p className="muted small">{t("pk.vis.no_bay")}</p> : <div className="grid g2"><Field label={t("pk.vis.plate")}><input className="input" value={plate} onChange={(e) => setPlate(e.target.value)} /></Field>
        <Field label={t("pk.vis.bay")}><select className="input" value={bay || String(free[0]?.id)} onChange={(e) => setBay(e.target.value)}>{free.map((b) => <option key={b.id} value={b.id}>{b.code}</option>)}</select></Field></div>}
      {free.length > 0 && <Btn onClick={logIn} disabled={plate.trim().length < 2}>{t("pk.vis.in")}</Btn>}
      {err && <p className="error" role="alert">{err}</p>}
    </Card>
    <div style={{ gridColumn: "1 / -1" }}><Card><div className="row between wrap"><h3 style={{ margin: 0 }}>{t("pk.vis.log")}</h3><label className="row"><input type="checkbox" checked={openOnly} onChange={(e) => { setOpenOnly(e.target.checked); setPage(1); }} /> {t("pk.vis.open")}</label></div>
      {!vis ? <p className="muted">{t("common.loading")}</p> : vis.items.length === 0 ? <Empty>{t("pk.vis.none")}</Empty> : vis.items.map((v) => (
        <div key={v.id} className="row between wrap" style={{ padding: "8px 0", borderTop: "1px solid var(--line)" }}><div><b>{v.plate}</b> <span className="small muted">· {v.slot}</span><br /><span className="small muted">{t("pk.vis.in_at", { t: ftime(v.in_at) })}{v.out_at ? ` · ${t("pk.vis.out_at", { t: ftime(v.out_at) })}` : ""}</span></div>
          {!v.out_at && <Btn size="sm" variant="soft" onClick={() => out(v.id)}>{t("pk.vis.out")}</Btn>}</div>))}
      {vis && <Pager page={page} size={vis.size} total={vis.total} onPage={setPage} />}</Card></div>
    {toast.node}
  </div>);
}

function Settings({ size, onSaved }: { size: number; onSaved: () => void }) {
  const { t } = useT(); const [n, setN] = useState(size); const [err, setErr] = useState(""); const toast = useToast();
  useEffect(() => setN(size), [size]);
  const save = async () => { try { await api("/parking/settings", { method: "PUT", body: { page_size: n } }); toast.show(t("pk.done")); onSaved(); } catch (e: any) { setErr(e.message); } };
  return <Card style={{ maxWidth: 460 }}><h3 style={{ marginTop: 0 }}>{t("pk.set.title")}</h3><Field label={t("pk.set.title")} hint={t("pk.set.hint")}><input className="input" type="number" min={6} max={100} value={n} onChange={(e) => setN(+e.target.value)} /></Field>
    {err && <p className="error" role="alert">{err}</p>}<Btn onClick={save}>{t("pk.set.save")}</Btn>{toast.node}</Card>;
}

export default function Parking() {
  const { t } = useT(); const { prop, has } = useAuth();
  const resident = has("FLAT_OWNER", "TENANT", "OWNER_REP"); const manage = has("PROPERTY_ADMIN", "AGENCY_MANAGER"); const see = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY", "TREASURER", "MEMBER", "AUDITOR", "CARETAKER", "GUARD");
  const watch = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "GUARD"); const vehicles = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY", "TREASURER", "MEMBER", "AUDITOR", "CARETAKER");
  const tabs = [resident && { id: "mine", label: t("pk.tab.mine") }, see && { id: "map", label: t("pk.tab.map") }, see && { id: "handover", label: t("pk.tab.handover") }, vehicles && { id: "vehicles", label: t("pk.tab.vehicles") },
    watch && { id: "gate", label: t("pk.tab.gate") }, manage && { id: "settings", label: t("pk.tab.settings") }].filter(Boolean) as { id: string; label: string }[];
  const [tab, setTab] = useState(""); const [sum, setSum] = useState<Sum | null>(null);
  const cur = tabs.find((x) => x.id === tab)?.id ?? tabs[0]?.id;
  const loadSum = useCallback(() => { if (see) api<Sum>("/parking/summary").then(setSum).catch(() => setSum(null)); }, [see]);
  useEffect(() => { loadSum(); }, [loadSum, prop?.id]);
  return (<>
    <PageHead title={t("pk.title")} sub={t(see ? "pk.sub" : "pk.sub_mine")} />
    {tabs.length > 1 && <div style={{ marginBottom: 14 }}><Tabs value={cur ?? ""} onChange={setTab} items={tabs} /></div>}
    {sum && cur !== "mine" && cur !== "gate" && <div className="grid g4" style={{ marginBottom: 16 }}>
      <Stat label={t("pk.stat.slots")} value={sum.slots} note={`${sum.visitor} ${t("pk.state.visitor").toLowerCase()} · ${sum.blocked} ${t("pk.state.blocked").toLowerCase()}`} /><Stat label={t("pk.stat.free")} value={sum.free} />
      <Stat label={t("pk.stat.unmet")} value={<span style={{ color: sum.flats_unmet ? "var(--warn)" : undefined }}>{sum.flats_unmet}</span>} /><Stat label={t("pk.stat.vehicles")} value={sum.vehicles} note={sum.to_review ? `${sum.to_review} ${t("pk.stat.review").toLowerCase()}` : undefined} /></div>}
    {cur === "mine" && <MyParking />}
    {cur === "map" && <SlotMap manage={manage} onChanged={loadSum} />}
    {cur === "handover" && <Handover />}
    {cur === "vehicles" && <Vehicles />}
    {cur === "gate" && <Gate />}
    {cur === "settings" && <Settings size={sum?.page_size ?? 24} onSaved={loadSum} />}
  </>);
}
