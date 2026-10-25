"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Bar, Btn, Card, Chip, Field, PageHead, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import { CHARGE_DEFAULTS, REMINDER_KEY, REMINDER_STEPS, SETUP_STEPS, type SetupState, type SetupStep } from "@/lib/setupDefaults";

const ROLES = ["PRESIDENT", "SECRETARY", "TREASURER", "MEMBER"];
type Row = { name: string; email: string; phone: string; role: string };
type Result = { email: string; role: string; ok: boolean; temp_password: string | null; error: string };

export function SetupWizard() {
  const { t, pick } = useT(); const { prop, reload, has } = useAuth(); const router = useRouter(); const toast = useToast();
  const [s, setS] = useState<SetupState | null>(null); const [cur, setCur] = useState<SetupStep>("building"); const [busy, setBusy] = useState(false); const [editing, setEditing] = useState(false);
  const load = useCallback(async () => { const d = await api<SetupState>("/setup"); setS(d); return d; }, []);
  useEffect(() => { load().then((d) => { if (d.applicable) setCur(d.next_step ?? "review"); }).catch(() => setS({ applicable: false } as SetupState)); }, [load, prop?.id]);

  // form state, seeded from what FlatWise already knows
  const [b, setB] = useState({ name: "", name_bn: "", address: "", city: "", floors: "" });
  const [fl, setFl] = useState({ floors: "", blocks: "A", per: "4", area: "1200", beds: "3", cars: "0", bikes: "0" });
  const [ch, setCh] = useState(CHARGE_DEFAULTS.map((c) => ({ ...c, bdt: String(c.bdt) })));
  const [due, setDue] = useState("10"); const [remOn, setRemOn] = useState(true); const [remSteps, setRemSteps] = useState<string[]>([...REMINDER_STEPS]);
  const [rows, setRows] = useState<Row[]>([{ name: "", email: "", phone: "", role: "PRESIDENT" }]); const [results, setResults] = useState<Result[] | null>(null);
  useEffect(() => {
    if (!s?.applicable) return;
    const k = s.known.building;
    setB({ name: k.name, name_bn: k.name_bn, address: k.address, city: k.city, floors: k.floors ? String(k.floors) : "" });
    setFl((f) => ({ ...f, floors: k.floors ? String(k.floors) : f.floors }));
    if (s.known.due_day) setDue(String(s.known.due_day));
    if (s.data.reminders) { setRemOn(s.data.reminders.enabled); setRemSteps(s.data.reminders.steps); }
  }, [s?.applicable]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!s) return <p className="muted">{t("common.loading")}</p>;
  if (!s.applicable) return <Card><p>{t("su.not_needed")}</p><Link className="btn btn-primary" href="/app">{t("su.to_dash")}</Link></Card>;

  const idx = SETUP_STEPS.indexOf(cur);
  const state = (st: SetupStep) => s.steps.find((x) => x.step === st)?.state ?? "todo";
  const known = state(cur) === "known" && !editing;
  const go = (st: SetupStep) => { setEditing(false); setResults(null); setCur(st); window.scrollTo({ top: 0 }); };
  const after = async () => { const d = await load(); const i = SETUP_STEPS.indexOf(cur); go(SETUP_STEPS[Math.min(i + 1, SETUP_STEPS.length - 1)]); return d; };
  const mark = (st: SetupStep, state: "done" | "skipped") => api<SetupState>(`/setup/steps/${st}`, { method: "PUT", body: { state } });
  const run = async (fn: () => Promise<void>) => { setBusy(true); try { await fn(); } catch (e: any) { toast.show(t("su.err", { e: e.message })); } finally { setBusy(false); } };
  const skip = () => run(async () => { await mark(cur, "skipped"); await after(); });
  const num = (v: string) => Number(v) || 0;
  const area = num(fl.area) || 1200;
  const estimate = ch.filter((c) => c.on).reduce((sum, c) => sum + (c.kind === "per_sqft" ? Number(c.bdt) * area : Number(c.bdt)), 0);
  const blocks = fl.blocks.split(",").map((x) => x.trim()).filter(Boolean);
  const flatCount = num(fl.floors) * Math.max(1, blocks.length) * num(fl.per);

  const save = () => run(async () => {
    if (cur === "building") { await api("/property", { method: "PUT", body: { name: b.name, name_bn: b.name_bn, address: b.address, city: b.city, floors: num(b.floors) } }); await reload(); await mark("building", "done"); await after(); }
    else if (cur === "flats") {
      await api("/units/generate", { body: { floors: num(fl.floors), blocks, per_block: num(fl.per), area_sqft: num(fl.area), bedrooms: num(fl.beds), cars_per_flat: s.features.includes("parking") ? num(fl.cars) : 0, bikes_per_flat: s.features.includes("parking") ? num(fl.bikes) : 0 } });
      await mark("flats", "done"); await after();
    } else if (cur === "charges") {
      const picked = ch.filter((c) => c.on);
      if (!picked.length) { toast.show(t("su.c.none")); return; }
      for (const c of picked) await api("/billing/rules", { body: { name: c.name, name_bn: c.name_bn, kind: c.kind, amount: Math.round(Number(c.bdt) * 100), active: true } });
      await mark("charges", "done"); await after();
    } else if (cur === "reminders") {
      await api("/setup/data", { method: "PUT", body: { due_day: num(due), reminders_enabled: remOn, reminder_steps: remSteps } }); await mark("reminders", "done"); await after();
    } else if (cur === "committee") {
      const filled = rows.filter((r) => r.name.trim() && r.email.trim());
      if (!filled.length) { await skip(); return; }
      const d = await api<{ results: Result[] }>("/setup/committee", { body: { members: filled } });
      setResults(d.results);
      if (d.results.some((r) => r.ok)) { await mark("committee", "done"); await load(); }
    } else if (cur === "review") { await api("/setup/complete", { method: "POST", body: undefined }); await reload(); toast.show(t("su.v.done")); router.push("/app"); }
  });

  const label = (st: SetupStep) => t(`su.s.${st}`);
  const chip = (st: SetupStep) => { const v = state(st); return <Chip tone={v === "done" || v === "known" ? "ok" : v === "skipped" ? "mute" : "warn"}>{t(`su.st.${v}`)}</Chip>; };
  const done = s.steps.filter((x) => x.state !== "todo").length;
  const f = (k: string, v: string, set: (o: any) => void, o: any) => set({ ...o, [k]: v });

  return (
    <>
      <PageHead helpKey="setup-wizard" title={t("su.title")} sub={t("su.sub")} />
      <Card style={{ marginBottom: 16 }}>
        <div className="row between small"><b>{t("su.step", { n: idx + 1, m: SETUP_STEPS.length })} · {label(cur)}</b><span className="muted">{t("su.percent", { n: s.percent })}</span></div>
        <div style={{ margin: "10px 0" }}><Bar pct={(done / SETUP_STEPS.length) * 100} spark /></div>
        <div className="row wrap" style={{ gap: 6 }}>{SETUP_STEPS.map((st, i) => <button key={st} className={`btn btn-sm ${st === cur ? "btn-primary" : "btn-ghost"}`} onClick={() => go(st)} aria-current={st === cur} aria-label={label(st)}>{i + 1}. {label(st)}</button>)}</div>
      </Card>

      <Card>
        <div className="row between wrap" style={{ marginBottom: 12 }}><h2>{label(cur)}</h2>{chip(cur)}</div>

        {known && cur !== "review" && (
          <div className="stack">
            <p><b>{t("su.known_title")}</b></p><p className="muted">{t("su.known_note")}</p>
            {cur === "building" && <p>{pick(s.known.building.name, s.known.building.name_bn)} · {s.known.building.address} · {t("su.b.floors")}: {s.known.building.floors}</p>}
            {cur === "flats" && <p>{t("su.f.have", { n: s.known.units })} {t("su.f.more")}</p>}
            {cur === "charges" && <p>{t("su.c.have", { n: s.known.rules })}</p>}
            {cur === "reminders" && <p>{t("su.r.due")}: <b>{s.known.due_day}</b></p>}
            {cur === "committee" && <p>{t("su.m.have", { n: s.known.committee })}</p>}
            <div className="row wrap"><Btn onClick={() => run(async () => { await mark(cur, "done"); await after(); })} disabled={busy}>{t("su.continue")}</Btn>{(cur === "building" || cur === "reminders" || cur === "committee") && <Btn variant="ghost" onClick={() => setEditing(true)}>{t("su.edit")}</Btn>}</div>
          </div>
        )}

        {!known && cur === "building" && (<div className="stack"><p className="muted">{t("su.b.sub")}</p>
          <div className="grid g2"><Field label={t("su.b.name")}><input className="input" value={b.name} onChange={(e) => f("name", e.target.value, setB, b)} /></Field><Field label={t("su.b.name_bn")}><input className="input" value={b.name_bn} onChange={(e) => f("name_bn", e.target.value, setB, b)} /></Field></div>
          <Field label={t("su.b.address")}><input className="input" value={b.address} onChange={(e) => f("address", e.target.value, setB, b)} /></Field>
          <div className="grid g2"><Field label={t("su.b.city")}><input className="input" value={b.city} onChange={(e) => f("city", e.target.value, setB, b)} /></Field><Field label={t("su.b.floors")}><input className="input" inputMode="numeric" value={b.floors} onChange={(e) => f("floors", e.target.value, setB, b)} /></Field></div></div>)}

        {!known && cur === "flats" && (<div className="stack"><p className="muted">{t("su.f.sub")}</p>
          <div className="grid g3"><Field label={t("su.f.floors")}><input className="input" inputMode="numeric" value={fl.floors} onChange={(e) => f("floors", e.target.value, setFl, fl)} /></Field><Field label={t("su.f.blocks")}><input className="input" value={fl.blocks} onChange={(e) => f("blocks", e.target.value, setFl, fl)} /></Field><Field label={t("su.f.per")}><input className="input" inputMode="numeric" value={fl.per} onChange={(e) => f("per", e.target.value, setFl, fl)} /></Field></div>
          <div className="grid g2"><Field label={t("su.f.area")}><input className="input" inputMode="numeric" value={fl.area} onChange={(e) => f("area", e.target.value, setFl, fl)} /></Field><Field label={t("su.f.beds")}><input className="input" inputMode="numeric" value={fl.beds} onChange={(e) => f("beds", e.target.value, setFl, fl)} /></Field></div>
          {s.features.includes("parking") ? <div className="grid g2"><Field label={t("su.f.cars")}><input className="input" inputMode="numeric" value={fl.cars} onChange={(e) => f("cars", e.target.value, setFl, fl)} /></Field><Field label={t("su.f.bikes")}><input className="input" inputMode="numeric" value={fl.bikes} onChange={(e) => f("bikes", e.target.value, setFl, fl)} /></Field></div> : <p className="small muted">{t("su.f.parking_off")}</p>}
          <p><b>{t("su.f.total", { n: flatCount })}</b></p></div>)}

        {!known && cur === "charges" && (s.features.includes("billing") ? (<div className="stack"><p className="muted">{t("su.c.sub")}</p>
          {ch.map((c, i) => (
            <div key={c.key} className="row wrap" style={{ gap: 12, padding: "6px 0", borderBottom: "1px solid var(--line)" }}>
              <label className="row" style={{ gap: 8, flex: "1 1 220px" }}><input type="checkbox" checked={c.on} onChange={(e) => setCh(ch.map((x, j) => (j === i ? { ...x, on: e.target.checked } : x)))} aria-label={t("su.c.use")} /><span><b>{pick(c.name, c.name_bn)}</b><br /><span className="small muted">{c.kind === "flat" ? t("su.c.flat") : t("su.c.sqft")}</span></span></label>
              <input className="input" style={{ width: 120 }} inputMode="decimal" aria-label={`${pick(c.name, c.name_bn)} ${t("su.c.amount")}`} value={c.bdt} disabled={!c.on} onChange={(e) => setCh(ch.map((x, j) => (j === i ? { ...x, bdt: e.target.value } : x)))} />
            </div>))}
          <p className="small muted">{t("su.c.example", { a: area, t: Math.round(estimate).toLocaleString("en-US") })}</p></div>) : <p className="muted">{t("su.c.nobilling")}</p>)}

        {!known && cur === "reminders" && (<div className="stack"><p className="muted">{t("su.r.sub")}</p>
          <Field label={t("su.r.due")} hint={t("su.r.due_hint")}><select className="input" style={{ maxWidth: 160 }} value={due} onChange={(e) => setDue(e.target.value)}>{Array.from({ length: 28 }, (_, i) => <option key={i + 1} value={i + 1}>{i + 1}</option>)}</select></Field>
          {s.features.includes("reminders") ? <>
            <label className="row" style={{ gap: 8 }}><input type="checkbox" checked={remOn} onChange={(e) => setRemOn(e.target.checked)} />{t("su.r.on")}</label>
            {remOn && <div><div className="small muted" style={{ marginBottom: 6 }}>{t("su.r.which")}</div><div className="row wrap" style={{ gap: 14 }}>{REMINDER_STEPS.map((k) => <label key={k} className="row" style={{ gap: 6 }}><input type="checkbox" checked={remSteps.includes(k)} onChange={(e) => setRemSteps(e.target.checked ? [...remSteps, k] : remSteps.filter((x) => x !== k))} />{t(REMINDER_KEY[k])}</label>)}</div></div>}
            <p className="small muted">{t("su.r.note")}</p></> : <p className="small muted">{t("su.r.noplan")}</p>}</div>)}

        {!known && cur === "committee" && (<div className="stack"><p className="muted">{t("su.m.sub")}</p>
          {results ? (<div className="stack"><h3>{t("su.m.done")}</h3><p className="small muted">{t("su.m.once")}</p>
            {results.map((r) => <div key={r.email} className="row wrap between" style={{ gap: 8, padding: "8px 0", borderBottom: "1px solid var(--line)" }}><span><b>{r.email}</b> <Chip>{t(`role.${r.role}`)}</Chip></span>
              {r.ok ? <span className="row" style={{ gap: 8 }}><span className="small muted">{t("su.m.temp")}:</span><code>{r.temp_password}</code><Btn size="sm" variant="ghost" onClick={() => { navigator.clipboard?.writeText(r.temp_password ?? ""); toast.show(t("su.m.copied")); }}>{t("su.m.copy")}</Btn></span> : <Chip tone="bad">{t("su.m.failed")}: {r.error}</Chip>}</div>)}
            <Btn onClick={() => go("review")}>{t("su.continue")}</Btn></div>) : (<>
            {rows.map((r, i) => (<div key={i} className="grid g2" style={{ gap: 10, paddingBottom: 12, borderBottom: "1px solid var(--line)" }}>
              <Field label={t("su.m.name")}><input className="input" value={r.name} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} /></Field>
              <Field label={t("su.m.email")}><input className="input" type="email" value={r.email} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, email: e.target.value } : x)))} /></Field>
              <Field label={t("su.m.phone")}><input className="input" inputMode="tel" value={r.phone} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, phone: e.target.value } : x)))} /></Field>
              <Field label={t("su.m.role")}><select className="input" value={r.role} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, role: e.target.value } : x)))}>{ROLES.map((x) => <option key={x} value={x}>{t(`role.${x}`)}</option>)}</select></Field>
              {rows.length > 1 && <div><Btn size="sm" variant="ghost" onClick={() => setRows(rows.filter((_, j) => j !== i))}>{t("su.m.remove")}</Btn></div>}</div>))}
            {rows.length < 8 && <Btn variant="soft" onClick={() => setRows([...rows, { name: "", email: "", phone: "", role: "MEMBER" }])}>{t("su.m.add")}</Btn>}
            <p className="small muted">{t("su.m.skip_note")}</p></>)}</div>)}

        {cur === "review" && (<div className="stack"><p className="muted">{t("su.v.sub")}</p>
          {SETUP_STEPS.filter((x) => x !== "review").map((st) => <div key={st} className="row between wrap" style={{ padding: "8px 0", borderBottom: "1px solid var(--line)" }}><b>{label(st)}</b><span className="row" style={{ gap: 8 }}>{chip(st)}<Btn size="sm" variant="ghost" onClick={() => { go(st); setEditing(false); }}>{t("su.edit")}</Btn></span></div>)}
          <h3 style={{ marginTop: 18 }}>{t("su.v.next")}</h3>
          <ul className="list-dot"><li><Link href="/app/units">{t("su.v.n1")}</Link></li>{has("PROPERTY_ADMIN", "AGENCY_MANAGER") && <li><Link href="/app/billing">{t("su.v.n2")}</Link></li>}<li><Link href="/app/help">{t("su.v.n3")}</Link></li></ul></div>)}

        {!(known && cur !== "review") && !(cur === "committee" && results) && (
          <div className="row wrap between" style={{ marginTop: 22, gap: 10 }}>
            <Btn variant="ghost" onClick={() => go(SETUP_STEPS[Math.max(0, idx - 1)])} disabled={idx === 0 || busy}>{t("su.back")}</Btn>
            <div className="row wrap" style={{ gap: 10 }}>
              {cur !== "review" && <Btn variant="ghost" onClick={skip} disabled={busy}>{t("su.skip")}</Btn>}
              <Btn onClick={save} disabled={busy || (cur === "charges" && !s.features.includes("billing"))}>{busy ? t("su.saving") : cur === "review" ? t("su.v.finish") : t("su.next")}</Btn>
            </div>
          </div>)}
      </Card>
      {toast.node}
    </>
  );
}
