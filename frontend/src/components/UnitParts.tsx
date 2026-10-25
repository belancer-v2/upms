"use client";
import { useEffect, useState } from "react";
import { Btn, Chip, Field, Modal } from "@/components/ui";
import { Avatar } from "@/components/Avatar";
import { PhotoPick, uploadPhotoFor } from "@/components/AvatarUploader";
import { ProfileModal } from "@/components/ProfilePanel";
import { api, fdate } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

export type Person = { id: number; kind: string; name: string; name_bn: string; phone: string; email: string; resides: boolean; has_login: boolean; start_date: string; end_date: string | null };
export type Unit = { id: number; block: string; floor: number; number: string; area_sqft: number; bedrooms: number; status: string; owners: Person[]; tenants: Person[]; history: Person[] };

export const statusTone = (s: string) => (s === "occupied" ? "" : s === "vacant" ? "mute" : s === "to_let" ? "ok" : "warn") as "" | "mute" | "ok" | "warn";
export function StatusChip({ s }: { s: string }) { const { t } = useT(); return <Chip tone={statusTone(s)}>{t(`unit.status.${s}`)}</Chip>; }

/** Window-grid map: one rounded square per flat, a floor per row. Colors follow flat status. */
export function UnitMap({ units, onPick, color }: { units: Unit[]; onPick: (u: Unit) => void; color?: (u: Unit) => { bg: string; fg: string; ring?: string } }) {
  const { t } = useT();
  const floors = Array.from(new Set(units.map((u) => u.floor))).sort((a, b) => b - a);
  const base = (u: Unit) => u.status === "occupied" ? { bg: "var(--blush)", fg: "var(--blush-text)" } : u.status === "vacant" ? { bg: "var(--surface2)", fg: "var(--muted)", ring: "var(--line)" } : u.status === "to_let" ? { bg: "var(--ok-bg)", fg: "var(--ok)" } : { bg: "var(--warn-bg)", fg: "var(--warn)" };
  return (
    <div className="stack" style={{ gap: 10 }}>
      {floors.map((f) => (
        <div key={f} className="row" style={{ gap: 14, alignItems: "stretch" }}>
          <div className="small muted" style={{ width: 64, fontWeight: 800, paddingTop: 12 }}>{t("unit.floor", { n: f })}</div>
          <div className="row wrap" style={{ gap: 10 }}>
            {units.filter((u) => u.floor === f).map((u) => { const c = (color ?? base)(u); return (
              <button key={u.id} onClick={() => onPick(u)} aria-label={`${u.number} ${t(`unit.status.${u.status}`)}`} style={{ width: 92, height: 56, borderRadius: 14, border: c.ring ? `2px solid ${c.ring}` : "2px solid transparent", background: c.bg, color: c.fg, font: "inherit", fontWeight: 800, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14 }}>{u.number}</button>); })}
          </div>
        </div>))}
    </div>
  );
}

export function PersonLine({ p, showContact }: { p: Person; showContact?: boolean }) {
  const { t, pick } = useT(); const [prof, setProf] = useState(false);
  return (
    <div className="row between" style={{ padding: "8px 0", borderTop: "1px solid var(--line)", gap: 12 }}>
      <div className="row" style={{ gap: 12, alignItems: "center" }}><button className="icon-btn" style={{ padding: 0 }} aria-label={`${t("prof.open")}: ${pick(p.name, p.name_bn)}`} onClick={() => setProf(true)}><Avatar kind="occupant" id={p.id} name={pick(p.name, p.name_bn)} size={40} /></button>
        {prof && <ProfileModal kind="occupant" id={p.id} name={pick(p.name, p.name_bn)} onClose={() => setProf(false)} />}
      <div><b>{pick(p.name, p.name_bn)}</b> {p.kind === "owner" && <span className="small muted">· {p.resides ? t("unit.lives") : t("unit.rented")}</span>}<br />
        <span className="small muted">{showContact && p.phone ? `${p.phone} · ` : ""}{p.end_date ? t("unit.till", { a: fdate(p.start_date), b: fdate(p.end_date) }) : t("unit.since", { d: fdate(p.start_date) })}</span></div></div>
      {p.has_login && <Chip tone="info">{t("unit.login")}</Chip>}
    </div>
  );
}

export function PersonForm({ unit, kinds, onDone, onClose }: { unit: Unit; kinds: ("owner" | "tenant")[]; onDone: (u: Unit, temp?: string | null) => void; onClose: () => void }) {
  const { t } = useT();
  const [f, setF] = useState({ kind: kinds[0], name: "", name_bn: "", phone: "", email: "", resides: true, create_login: false }); const [err, setErr] = useState(""); const [photo, setPhoto] = useState<File | null>(null); const [busy, setBusy] = useState(false);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value });
  const save = async () => {
    setBusy(true);
    try {
      const r = await api(`/units/${unit.id}/occupants`, { body: f });
      if (photo && r.occupant_id) { const m = await uploadPhotoFor("occupant", r.occupant_id, photo); if (m) window.alert(`${t("prof.photo")}: ${m}`); }
      onDone(r.unit, r.temp_password);
    } catch (e: any) { setErr(e.message); setBusy(false); }
  };
  return (
    <Modal title={`${t("unit.add_person")} · ${unit.number}`} onClose={onClose}>
      {kinds.length > 1 && <Field label={t("unit.person.kind")}><select className="input" value={f.kind} onChange={set("kind")}>{kinds.map((k) => <option key={k} value={k}>{t(`unit.${k}`)}</option>)}</select></Field>}
      <PhotoPick file={photo} onFile={setPhoto} name={f.name} />
      <Field label={t("unit.person.name")}><input className="input" value={f.name} onChange={set("name")} /></Field>
      <Field label={t("unit.person.name_bn")}><input className="input" value={f.name_bn} onChange={set("name_bn")} /></Field>
      <div className="grid g2"><Field label={t("unit.person.phone")}><input className="input" inputMode="tel" value={f.phone} onChange={set("phone")} /></Field><Field label={t("unit.person.email")}><input className="input" type="email" value={f.email} onChange={set("email")} /></Field></div>
      {f.kind === "owner" && <label className="row" style={{ marginBottom: 12 }}><input type="checkbox" checked={f.resides} onChange={set("resides")} /> {t("unit.person.resides")}</label>}
      <label className="row" style={{ marginBottom: 12 }}><input type="checkbox" checked={f.create_login} onChange={set("create_login")} /> {t("unit.person.login")}</label>
      {f.kind === "tenant" && <p className="hint">{t("unit.person.tenant_rule")}</p>}
      {err && <p className="error" role="alert">{err}</p>}
      <div className="row"><Btn onClick={save} disabled={busy || f.name.trim().length < 2}>{t("common.save")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div>
    </Modal>
  );
}

type PkView = { entitlement: Record<string, number>; held: Record<string, number>; slots: { id: number; code: string; kind: string; cover: string }[]; vehicles: { id: number; reg_no: string; kind: string; status: string; temporary: boolean }[] };
/** Parking at a glance inside the flat panel: slots held against what the flat is promised, and its vehicles. */
function ParkingSummary({ unitId }: { unitId: number }) {
  const { t } = useT(); const { has, feature } = useAuth(); const [d, setD] = useState<PkView | null>(null);
  const ok = feature("parking") && has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY", "TREASURER", "MEMBER", "AUDITOR", "CARETAKER", "FLAT_OWNER", "TENANT", "OWNER_REP");
  useEffect(() => { if (ok) api<PkView>(`/parking/units/${unitId}`).then(setD).catch(() => setD(null)); }, [ok, unitId]);
  if (!ok || !d) return null;
  const kinds = ["car", "motorbike", "bicycle"].filter((k) => (d.entitlement[k] ?? 0) > 0 || (d.held[k] ?? 0) > 0);
  return (<>
    <h3 style={{ margin: "16px 0 4px" }}>{t("pk.panel.title")}</h3>
    {kinds.length === 0 && d.vehicles.length === 0 ? <p className="muted small">{t("pk.no_slots")}</p> : <>
      <div className="row wrap" style={{ gap: 6 }}>{kinds.map((k) => <Chip key={k} tone={(d.held[k] ?? 0) < (d.entitlement[k] ?? 0) ? "warn" : "ok"}>{t("pk.ent_line", { k: t(`pk.kind.${k}`), h: d.held[k] ?? 0, e: d.entitlement[k] ?? 0 })}</Chip>)}</div>
      {d.slots.length > 0 && <p className="small" style={{ margin: "8px 0 0" }}>{t("pk.slots")}: {d.slots.map((s) => s.code).join(", ")}</p>}
      {d.vehicles.length > 0 && <p className="small" style={{ margin: "4px 0 0" }}>{t("pk.veh")}: {d.vehicles.map((v) => <span key={v.id} style={{ marginInlineEnd: 8 }}>{v.reg_no}{v.status === "to_review" && <> <Chip tone="warn">{t("pk.veh_review")}</Chip></>}</span>)}</p>}</>}
  </>);
}

export function UnitPanel({ unit, onClose, onChange, afterBlock }: { unit: Unit; onClose: () => void; onChange: (u: Unit, temp?: string | null) => void; afterBlock?: React.ReactNode }) {
  const { t } = useT(); const { has } = useAuth(); const [adding, setAdding] = useState(false);
  const manage = has("PROPERTY_ADMIN", "AGENCY_MANAGER"); const contacts = has("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY", "TREASURER", "MEMBER", "CARETAKER");
  const owner = has("FLAT_OWNER", "OWNER_REP");
  const call = async (path: string, method = "POST") => { const r = await api(path, { method }); onChange(r); };
  return (
    <Modal title={`${t("unit.number")} ${unit.number}`} onClose={onClose}>
      <div className="row wrap" style={{ marginBottom: 14 }}><StatusChip s={unit.status} /><span className="small muted">{t("unit.floor", { n: unit.floor })} · {unit.area_sqft} sq ft · {unit.bedrooms} {t("unit.beds").toLowerCase()}</span></div>
      {unit.status === "to_let_pending" && <p className="small" style={{ background: "var(--warn-bg)", color: "var(--warn)", padding: 10, borderRadius: 12, fontWeight: 700 }}>{t("unit.pending_note")}</p>}
      <h3 style={{ margin: "8px 0 4px" }}>{t("unit.owners")}</h3>
      {unit.owners.map((p) => <PersonLine key={p.id} p={p} showContact={contacts} />)}
      <h3 style={{ margin: "16px 0 4px" }}>{t("unit.tenants")}</h3>
      {unit.tenants.length ? unit.tenants.map((p) => <div key={p.id}><PersonLine p={p} showContact={contacts} />{(manage || owner) && <Btn size="sm" variant="ghost" onClick={() => confirm(t("unit.confirm_move", { n: p.name })) && call(`/occupants/${p.id}/move-out`)}>{t("unit.move_out")}</Btn>}</div>) : <p className="muted small">{t("unit.none_tenant")}</p>}
      {unit.history.length > 0 && <><h3 style={{ margin: "16px 0 4px" }}>{t("unit.history")}</h3>{unit.history.map((p) => <PersonLine key={p.id} p={p} />)}</>}
      <ParkingSummary unitId={unit.id} />
      {afterBlock}
      <div className="row wrap" style={{ marginTop: 18 }}>
        {manage && <Btn onClick={() => setAdding(true)}>{t("unit.add_person")}</Btn>}
        {!manage && owner && unit.tenants.length === 0 && <Btn onClick={() => setAdding(true)}>{t("myflat.add_tenant")}</Btn>}
        {manage && unit.status === "vacant" && <Btn variant="soft" onClick={() => call(`/units/${unit.id}/to-let/request`)}>{t("unit.offer")}</Btn>}
        {owner && unit.status === "to_let_pending" && <Btn onClick={() => call(`/units/${unit.id}/to-let/approve`)}>{t("unit.approve")}</Btn>}
        {(manage || owner) && (unit.status === "to_let" || unit.status === "to_let_pending") && <Btn variant="ghost" onClick={() => call(`/units/${unit.id}/to-let/withdraw`)}>{t("unit.withdraw")}</Btn>}
      </div>
      {manage && unit.status === "vacant" && <p className="hint" style={{ marginTop: 8 }}>{t("unit.offer_note")}</p>}
      {adding && <PersonForm unit={unit} kinds={manage ? ["owner", "tenant"] : ["tenant"]} onClose={() => setAdding(false)} onDone={(u, temp) => { setAdding(false); onChange(u, temp); }} />}
    </Modal>
  );
}
