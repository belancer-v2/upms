"use client";
import { useCallback, useEffect, useState } from "react";
import { Avatar, type PersonKind } from "@/components/Avatar";
import { AvatarUploader } from "@/components/AvatarUploader";
import { Btn, Field, Modal } from "@/components/ui";
import { api, fdate } from "@/lib/api";
import { useT } from "@/lib/i18n";

const BLOOD = ["", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"];
type D = { about: string; dob: string | null; blood_group: string; profession: string; emergency_name: string; emergency_phone: string; address: string; languages: string[] };
type P = { kind: PersonKind; id: number; name: string; name_bn: string; has_photo: boolean; photo_ver: number; can_edit: boolean; can_see_details: boolean; details: D | null };

/** Photo and optional details of one person. Editable when the server says so; read-only otherwise; name and photo only when details are private. */
export function ProfilePanel({ kind, id, onSaved }: { kind: PersonKind; id: number; onSaved?: () => void }) {
  const { t, pick } = useT(); const [p, setP] = useState<P | null>(null); const [f, setF] = useState<any>(null); const [err, setErr] = useState(""); const [ok, setOk] = useState(false);
  const load = useCallback(async () => { const r = await api<P>(`/profiles/${kind}/${id}`); setP(r); setF(r.details ? { ...r.details, dob: r.details.dob ?? "", languages: r.details.languages.join(", ") } : null); }, [kind, id]);
  useEffect(() => { load().catch((e) => setErr(e.message)); }, [load]);
  if (!p) return err ? <p className="error">{err}</p> : <p className="muted">…</p>;
  const name = pick(p.name, p.name_bn || p.name);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => { setOk(false); setF({ ...f, [k]: e.target.value }); };
  const save = async () => {
    setErr(""); setOk(false);
    try { await api(`/profiles/${kind}/${id}`, { method: "PUT", body: { ...f, dob: f.dob || null, languages: String(f.languages).split(",").map((x) => x.trim()).filter(Boolean) } }); setOk(true); await load(); onSaved?.(); }
    catch (e: any) { setErr(e.message); }
  };
  const d = p.details;
  return (
    <div className="stack">
      {p.can_edit
        ? <AvatarUploader kind={kind} id={id} name={name} hasPhoto={p.has_photo} ver={p.photo_ver} onChange={(r) => { setP({ ...p, has_photo: r.has_photo, photo_ver: r.photo_ver }); onSaved?.(); }} />
        : <div className="row" style={{ gap: 14 }}><Avatar kind={kind} id={id} name={name} size={84} ver={p.has_photo ? p.photo_ver : 0} /><h3 style={{ margin: 0 }}>{name}</h3></div>}
      {!p.can_see_details && <p className="hint">{t("prof.photo_only")}</p>}
      {p.can_see_details && p.can_edit && f && (<>
        <h3 style={{ margin: "6px 0 0" }}>{t("prof.details")}</h3><p className="hint" style={{ margin: 0 }}>{t("prof.optional")} {t("prof.private")}</p>
        <Field label={t("prof.about")} hint={t("prof.about_hint")}><textarea className="input" rows={3} maxLength={300} value={f.about} onChange={set("about")} /></Field>
        <div className="grid g2">
          <Field label={t("prof.dob")}><input className="input" type="date" value={f.dob} max={new Date().toISOString().slice(0, 10)} onChange={set("dob")} /></Field>
          <Field label={t("prof.blood")}><select className="input" value={f.blood_group} onChange={set("blood_group")}>{BLOOD.map((b) => <option key={b} value={b}>{b || t("prof.not_set")}</option>)}</select></Field>
          <Field label={t("prof.job")}><input className="input" value={f.profession} onChange={set("profession")} /></Field>
          <Field label={t("prof.langs")} hint={t("prof.langs_hint")}><input className="input" value={f.languages} onChange={set("languages")} /></Field>
          <Field label={t("prof.em_name")}><input className="input" value={f.emergency_name} onChange={set("emergency_name")} /></Field>
          <Field label={t("prof.em_phone")}><input className="input" inputMode="tel" value={f.emergency_phone} onChange={set("emergency_phone")} /></Field>
        </div>
        <Field label={t("prof.address")}><input className="input" value={f.address} onChange={set("address")} /></Field>
        {err && <p className="error" role="alert">{err}</p>}
        <div className="row"><Btn onClick={save}>{t("common.save")}</Btn>{ok && <span className="small" role="status" style={{ color: "var(--ok)" }}>{t("prof.saved")}</span>}</div>
      </>)}
      {p.can_see_details && !p.can_edit && d && (
        <dl className="kv">
          {d.about && <><dt>{t("prof.about")}</dt><dd>{d.about}</dd></>}
          {d.dob && <><dt>{t("prof.dob")}</dt><dd>{fdate(d.dob)}</dd></>}
          {d.blood_group && <><dt>{t("prof.blood")}</dt><dd>{d.blood_group}</dd></>}
          {d.profession && <><dt>{t("prof.job")}</dt><dd>{d.profession}</dd></>}
          {d.languages.length > 0 && <><dt>{t("prof.langs")}</dt><dd>{d.languages.join(", ")}</dd></>}
          {(d.emergency_name || d.emergency_phone) && <><dt>{t("prof.em_name")}</dt><dd>{[d.emergency_name, d.emergency_phone].filter(Boolean).join(" · ")}</dd></>}
          {d.address && <><dt>{t("prof.address")}</dt><dd>{d.address}</dd></>}
          {!Object.values(d).some((x) => (Array.isArray(x) ? x.length : x)) && <dd>{t("prof.none")}</dd>}
        </dl>)}
      {err && !f && <p className="error" role="alert">{err}</p>}
    </div>
  );
}

export function ProfileModal({ kind, id, name, onClose, onSaved }: { kind: PersonKind; id: number; name: string; onClose: () => void; onSaved?: () => void }) {
  const { t } = useT();
  return <Modal title={t("prof.edit_for", { n: name })} onClose={onClose}><ProfilePanel kind={kind} id={id} onSaved={onSaved} /></Modal>;
}
