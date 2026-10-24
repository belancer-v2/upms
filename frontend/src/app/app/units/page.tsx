"use client";
import { useCallback, useEffect, useState } from "react";
import { StatusChip, UnitMap, UnitPanel, type Unit } from "@/components/UnitParts";
import { Btn, Card, Chip, DataTable, Field, Modal, PageHead, Stat, Tabs, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type Sum = { units: number; occupied: number; vacant: number; to_let: number; to_let_pending: number; owners: number; tenants: number };

function AddFlats({ onClose, onDone }: { onClose: () => void; onDone: (msg: string) => void }) {
  const { t } = useT(); const [tab, setTab] = useState("gen");
  const [g, setG] = useState({ floors: 8, blocks: "A,B", per_block: 2, area_sqft: 1200 }); const [one, setOne] = useState({ block: "", floor: 1, number: "", area_sqft: 1200 }); const [csv, setCsv] = useState(""); const [err, setErr] = useState("");
  const run = async () => {
    try {
      if (tab === "gen") { const r = await api("/units/generate", { body: { ...g, blocks: g.blocks.split(",").map((x) => x.trim()).filter(Boolean) } }); onDone(t("unit.gen_done", { n: r.created })); }
      else if (tab === "one") { await api("/units", { body: one }); onDone(t("unit.person.saved")); }
      else {
        const rows = csv.split("\n").map((l) => l.split(/\t|,/).map((x) => x.trim())).filter((c) => c[0] && !/^number$/i.test(c[0])).map((c) => ({ number: c[0], floor: Number(c[1]) || 1, block: c[2] || "", area_sqft: Number(c[3]) || 0, bedrooms: Number(c[4]) || 3, owner_name: c[5] || "", owner_phone: c[6] || "" }));
        const r = await api("/units/import", { body: rows }); onDone(t("unit.import_done", { c: r.created, u: r.updated }));
      }
    } catch (e: any) { setErr(e.message); }
  };
  return (
    <Modal title={t("unit.add")} onClose={onClose}>
      <Tabs value={tab} onChange={setTab} items={[{ id: "gen", label: t("unit.gen") }, { id: "one", label: t("unit.one") }, { id: "csv", label: t("unit.import") }]} />
      <div style={{ marginTop: 18 }}>
        {tab === "gen" && <div className="grid g2"><Field label={t("unit.gen_floors")}><input className="input" type="number" value={g.floors} onChange={(e) => setG({ ...g, floors: +e.target.value })} /></Field><Field label={t("unit.gen_blocks")}><input className="input" value={g.blocks} onChange={(e) => setG({ ...g, blocks: e.target.value })} /></Field>
          <Field label={t("unit.gen_per")}><input className="input" type="number" value={g.per_block} onChange={(e) => setG({ ...g, per_block: +e.target.value })} /></Field><Field label={t("unit.area")}><input className="input" type="number" value={g.area_sqft} onChange={(e) => setG({ ...g, area_sqft: +e.target.value })} /></Field></div>}
        {tab === "one" && <div className="grid g2"><Field label={t("unit.number")}><input className="input" placeholder="A-501" value={one.number} onChange={(e) => setOne({ ...one, number: e.target.value })} /></Field><Field label={t("unit.block")}><input className="input" value={one.block} onChange={(e) => setOne({ ...one, block: e.target.value })} /></Field>
          <Field label={t("unit.floor", { n: "" }).trim()}><input className="input" type="number" value={one.floor} onChange={(e) => setOne({ ...one, floor: +e.target.value })} /></Field><Field label={t("unit.area")}><input className="input" type="number" value={one.area_sqft} onChange={(e) => setOne({ ...one, area_sqft: +e.target.value })} /></Field></div>}
        {tab === "csv" && <Field label={t("unit.import")} hint={t("unit.import_hint")}><textarea className="input" style={{ minHeight: 170, fontFamily: "monospace" }} placeholder={"A-101, 1, A, 1250, 3, Abdur Rahman, 01711000000"} value={csv} onChange={(e) => setCsv(e.target.value)} /></Field>}
      </div>
      {err && <p className="error" role="alert">{err}</p>}
      <div className="row"><Btn onClick={run}>{tab === "gen" ? t("unit.gen_do") : tab === "one" ? t("common.save") : t("unit.import_do")}</Btn><Btn variant="ghost" onClick={onClose}>{t("common.cancel")}</Btn></div>
    </Modal>
  );
}

export default function Units() {
  const { t, pick } = useT(); const { prop, has } = useAuth(); const toast = useToast();
  const [units, setUnits] = useState<Unit[]>([]); const [sum, setSum] = useState<Sum | null>(null); const [view, setView] = useState("map"); const [open, setOpen] = useState<Unit | null>(null); const [add, setAdd] = useState(false);
  const load = useCallback(async () => { setUnits(await api("/units")); setSum(await api("/units/summary").catch(() => null)); }, []);
  useEffect(() => { load(); }, [load, prop?.id]);
  const changed = async (u: Unit, temp?: string | null) => { await load(); setOpen(u); if (temp) toast.show(t("unit.person.temp", { pw: temp })); };
  return (
    <>
      <PageHead title={t("unit.title")} sub={t("unit.sub")} actions={<>{has("PROPERTY_ADMIN", "AGENCY_MANAGER") && <Btn onClick={() => setAdd(true)}>{t("unit.add")}</Btn>}<Tabs value={view} onChange={setView} items={[{ id: "map", label: t("unit.map") }, { id: "list", label: t("unit.list") }]} /></>} />
      {sum && <div className="grid g4" style={{ marginBottom: 22 }}>
        <Stat label={t("unit.summary.units")} value={sum.units} /><Stat label={t("unit.summary.occupied")} value={sum.occupied} note={`${sum.units ? Math.round((100 * sum.occupied) / sum.units) : 0}%`} />
        <Stat label={t("unit.summary.vacant")} value={sum.vacant + sum.to_let + sum.to_let_pending} note={`${t("unit.status.to_let")}: ${sum.to_let} · ${t("unit.status.to_let_pending")}: ${sum.to_let_pending}`} /><Stat label={t("unit.summary.owners")} value={sum.owners} note={`${t("unit.summary.tenants")}: ${sum.tenants}`} /></div>}
      {view === "map" ? (
        <Card><div className="row wrap" style={{ gap: 8, marginBottom: 18 }}><span className="small muted">{t("unit.legend")}</span>{["occupied", "vacant", "to_let", "to_let_pending"].map((s) => <StatusChip key={s} s={s} />)}</div><UnitMap units={units} onPick={setOpen} /></Card>
      ) : (
        <DataTable rows={units} onRow={setOpen} pageSize={12} search={(u) => `${u.number} ${[...u.owners, ...u.tenants].map((p) => p.name).join(" ")}`} cols={[
          { key: "number", head: t("unit.number"), render: (u) => <b>{u.number}</b> }, { key: "floor", head: t("unit.floor", { n: "" }).trim(), num: true }, { key: "area_sqft", head: t("unit.area"), num: true },
          { key: "owner", head: t("unit.owner"), render: (u) => u.owners[0] ? pick(u.owners[0].name, u.owners[0].name_bn) : "–" }, { key: "tenant", head: t("unit.tenant"), render: (u) => u.tenants[0] ? pick(u.tenants[0].name, u.tenants[0].name_bn) : <span className="muted">–</span> },
          { key: "status", head: t("common.status"), render: (u) => <StatusChip s={u.status} /> }]} />
      )}
      {open && <UnitPanel unit={open} onClose={() => setOpen(null)} onChange={changed} />}
      {add && <AddFlats onClose={() => setAdd(false)} onDone={(m) => { setAdd(false); toast.show(m); load(); }} />}
      {toast.node}
    </>
  );
}
