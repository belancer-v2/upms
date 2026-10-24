"use client";
import { use, useCallback, useEffect, useState } from "react";
import { Logo } from "@/components/Logo";
import { Toggles } from "@/components/Toggles";
import { Btn, Chip, Field } from "@/components/ui";
import { fdate, money } from "@/lib/api";
import { useT } from "@/lib/i18n";

type D = { id: number; kind: string; filename: string; status: string; note: string };
type V = { building: string; building_bn: string; unit: string; name: string; rent: number; advance: number; start_date: string; status: string; locked: boolean; details: Record<string, any>; nid: string; docs: D[]; missing: { fields: string[]; docs: string[] } };
const REQ = ["nid_front", "nid_back", "photo"]; const OPT = ["agreement", "noc", "employer"];

async function call(token: string, path = "", init?: RequestInit) {
  const r = await fetch(`/api/onboarding/link/${token}${path}`, init);
  if (!r.ok) { let m = r.statusText; try { const j = await r.json(); m = typeof j.detail === "string" ? j.detail : m; } catch {} throw new Error(m); }
  return r.json();
}

export default function TenantForm({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params); const { t, pick } = useT(); const [v, setV] = useState<V | null>(null); const [bad, setBad] = useState(false); const [step, setStep] = useState(1); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const [f, setF] = useState<Record<string, string>>({}); const [fam, setFam] = useState<{ name: string; relation: string; age: string }[]>([]);
  const load = useCallback(async () => { try { const x: V = await call(token); setV(x); setF((o) => ({ father_name: "", mother_name: "", permanent_address: "", previous_address: "", profession: "", employer: "", emergency_name: "", emergency_phone: "", reference_name: "", reference_phone: "", nid: "", ...Object.fromEntries(Object.entries(x.details).filter(([k]) => k !== "family")), ...Object.fromEntries(Object.entries(o).filter(([, val]) => val)) })); setFam((o) => (o.length ? o : x.details.family ?? [])); } catch { setBad(true); } }, [token]);
  useEffect(() => { load(); }, [load]);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  const save = async () => { setErr(""); await call(token, "", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...f, family: fam }) }); await load(); };
  const next = async () => { setBusy(true); try { await save(); setStep(step + 1); } catch (e: any) { setErr(e.message); } setBusy(false); };
  const upload = async (kind: string, file: File | null) => { if (!file) return; setBusy(true); setErr(""); try { const fd = new FormData(); fd.append("kind", kind); fd.append("file", file); await call(token, "/docs", { method: "POST", body: fd }); await load(); } catch (e: any) { setErr(e.message); } setBusy(false); };
  const send = async () => { setBusy(true); setErr(""); try { await save(); await call(token, "/submit", { method: "POST" }); await load(); } catch (e: any) { setErr(e.message); } setBusy(false); };
  const head = <div className="row between" style={{ marginBottom: 20 }}><Logo /><Toggles /></div>;
  if (bad) return <div style={{ maxWidth: 560, margin: "0 auto", padding: 20 }}>{head}<div className="card"><p>{t("tf.bad_link")}</p></div></div>;
  if (!v) return <div style={{ maxWidth: 560, margin: "0 auto", padding: 20 }}>{head}<p className="muted">{t("common.loading")}</p></div>;
  const docs = Object.fromEntries(v.docs.map((d) => [d.kind, d])); const rejected = v.docs.some((d) => d.status === "rejected");
  const input = (k: string, label: string, p: Record<string, any> = {}) => <Field label={label}><input className="input" value={f[k] ?? ""} onChange={set(k)} {...p} /></Field>;
  const miss = [...v.missing.fields.map((x) => t(`ob.fld.${x}`)), ...v.missing.docs.map((x) => t(`ob.doc.${x}`))];
  return (<div style={{ maxWidth: 560, margin: "0 auto", padding: "20px 16px 70px" }}>{head}
    <div className="card">
      <div className="eyebrow">{t("tf.title")}</div><h1 style={{ fontSize: 24, margin: "6px 0" }}>{t("tf.hello", { n: v.name })}</h1>
      <p className="muted small">{t("tf.intro", { b: pick(v.building, v.building_bn || v.building), u: v.unit })}</p><p className="small"><b>{t("tf.your_rent")}:</b> {money(v.rent)} · {fdate(v.start_date)}</p>
      {v.locked ? <div style={{ marginTop: 16 }}><Chip tone="ok">{t("ob.st." + v.status)}</Chip><p style={{ marginTop: 10 }}>{v.status === "review" ? t("tf.sent") : t("tf.locked")}</p></div> : (<>
        <div className="row between small" style={{ margin: "14px 0 8px" }}><b>{t(`tf.s${step}`)}</b><span className="muted">{t("tf.step", { a: step, n: 5 })}</span></div>
        <div className="bar"><i style={{ width: `${step * 20}%` }} /></div>
        {rejected && <p className="hint" style={{ color: "var(--bad)" }}>{t("tf.back_to_fix")}</p>}
        <div style={{ marginTop: 16 }}>
          {step === 1 && <>{input("father_name", t("ob.fld.father_name"))}{input("mother_name", t("ob.fld.mother_name"))}{input("profession", t("ob.fld.profession"))}{input("employer", t("ob.fld.employer"))}
            <Field label={t("ob.fld.permanent_address")}><textarea className="input" rows={2} value={f.permanent_address ?? ""} onChange={set("permanent_address")} /></Field><Field label={t("ob.fld.previous_address")}><textarea className="input" rows={2} value={f.previous_address ?? ""} onChange={set("previous_address")} /></Field>
            <Field label={t("ob.fld.nid")} hint={v.nid ? t("tf.nid_saved", { m: v.nid }) : t("tf.nid_hint")}><input className="input" inputMode="numeric" value={f.nid ?? ""} onChange={set("nid")} /></Field></>}
          {step === 2 && <><p className="hint">{t("tf.family_none")}</p>{fam.map((m, i) => (<div key={i} className="grid g3" style={{ gap: 8, marginBottom: 8 }}><input className="input" placeholder={t("tf.family_name")} value={m.name} onChange={(e) => setFam(fam.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} /><input className="input" placeholder={t("tf.family_rel")} value={m.relation} onChange={(e) => setFam(fam.map((x, j) => j === i ? { ...x, relation: e.target.value } : x))} /><input className="input" placeholder={t("tf.family_age")} inputMode="numeric" value={m.age} onChange={(e) => setFam(fam.map((x, j) => j === i ? { ...x, age: e.target.value } : x))} /></div>))}
            <Btn variant="soft" onClick={() => setFam([...fam, { name: "", relation: "", age: "" }])}>{t("tf.family_add")}</Btn></>}
          {step === 3 && <>{input("emergency_name", t("ob.fld.emergency_name"))}{input("emergency_phone", t("ob.fld.emergency_phone"), { inputMode: "tel" })}{input("reference_name", t("ob.fld.reference_name"))}{input("reference_phone", t("ob.fld.reference_phone"), { inputMode: "tel" })}</>}
          {step === 4 && <><p className="hint">{t("tf.file_hint")}</p>{[...REQ, ...OPT].map((k) => { const d = docs[k]; return (<div key={k} className="row between wrap" style={{ padding: "10px 0", borderTop: "1px solid var(--line)", gap: 8 }}>
            <div><b>{t(`ob.doc.${k}`)}</b> <span className="small muted">· {t(REQ.includes(k) ? "ob.doc.required" : "ob.doc.optional")}</span>{d && <div className="small muted">{d.filename}{d.note && ` · ${d.note}`}</div>}</div>
            <div className="row">{d && <Chip tone={d.status === "rejected" ? "bad" : "ok"}>{d.status === "rejected" ? t("ob.doc.rejected") : t("tf.uploaded")}</Chip>}<label className="btn soft sm" style={{ cursor: "pointer" }}>{d ? t("tf.replace") : t("tf.upload")}<input type="file" accept="image/jpeg,image/png,application/pdf" style={{ display: "none" }} onChange={(e) => upload(k, e.target.files?.[0] ?? null)} /></label></div></div>); })}</>}
          {step === 5 && <><div className="small" style={{ lineHeight: 1.8 }}>{["father_name", "profession", "permanent_address", "emergency_name", "reference_name"].map((k) => <div key={k}><span className="muted">{t(`ob.fld.${k}`)}:</span> <b>{f[k] || "–"}</b></div>)}<div><span className="muted">{t("ob.fld.family")}:</span> <b>{fam.filter((m) => m.name).length}</b></div><div><span className="muted">{t("ob.docs")}:</span> <b>{v.docs.length}</b></div></div>
            {miss.length > 0 && <p className="hint" style={{ color: "var(--bad)" }}>{t("tf.fix_missing", { l: miss.join(", ") })}</p>}</>}
        </div>
        {err && <p className="error" role="alert">{err}</p>}
        <div className="row between" style={{ marginTop: 18 }}>{step > 1 ? <Btn variant="ghost" onClick={() => setStep(step - 1)}>{t("tf.back")}</Btn> : <span />}{step < 5 ? <Btn onClick={next} disabled={busy}>{t("tf.next")}</Btn> : <Btn onClick={send} disabled={busy || miss.length > 0}>{t("tf.send")}</Btn>}</div></>)}
    </div></div>);
}
