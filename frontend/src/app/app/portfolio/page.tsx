"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Bar, Btn, Card, Field, Modal, PageHead } from "@/components/ui";
import { api, store } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type B = { id: number; name: string; name_bn: string; city: string; address: string; units: number; occupied: number; vacant: number; owners: number; tenants: number; occupancy_pct: number };
export default function Portfolio() {
  const { t, pick } = useT(); const router = useRouter(); const { reload, setProp, has } = useAuth();
  const [rows, setRows] = useState<B[]>([]); const [add, setAdd] = useState(false); const [f, setF] = useState({ name: "", address: "", city: "Dhaka", floors: 8 });
  const load = () => api<B[]>("/portfolio").then(setRows);
  useEffect(() => { load(); }, []);
  const open = (id: number) => { setProp(id); store.prop = id; router.push("/app/units"); };
  const create = async () => { await api("/portfolio/buildings", { body: f }); setAdd(false); await reload(); load(); };
  return (<>
    <PageHead title={t("port.title")} sub={t("port.sub")} actions={has("AGENCY_MANAGER") && <Btn onClick={() => setAdd(true)}>{t("port.add")}</Btn>} />
    <div className="grid g3">{rows.map((b) => (
      <Card key={b.id}><h3>{pick(b.name, b.name_bn)}</h3><p className="small muted" style={{ margin: "2px 0 14px" }}>{b.address || b.city}</p>
        <div className="row between small"><b>{t("port.occupancy", { n: b.occupancy_pct })}</b><span className="muted">{t("port.flats", { n: b.units })}</span></div><div style={{ margin: "8px 0 14px" }}><Bar pct={b.occupancy_pct} spark /></div>
        <div className="row small muted" style={{ gap: 18 }}><span>{t("unit.summary.owners")}: <b style={{ color: "var(--text)" }}>{b.owners}</b></span><span>{t("unit.summary.tenants")}: <b style={{ color: "var(--text)" }}>{b.tenants}</b></span><span>{t("unit.summary.vacant")}: <b style={{ color: "var(--text)" }}>{b.vacant}</b></span></div>
        <div style={{ marginTop: 16 }}><Btn variant="soft" size="sm" onClick={() => open(b.id)}>{t("port.open")}</Btn></div></Card>))}</div>
    {add && <Modal title={t("port.add")} onClose={() => setAdd(false)}>
      <Field label={t("port.name")}><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field><Field label={t("port.address")}><input className="input" value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} /></Field>
      <div className="grid g2"><Field label={t("port.city")}><input className="input" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} /></Field><Field label={t("port.floors")}><input className="input" type="number" value={f.floors} onChange={(e) => setF({ ...f, floors: +e.target.value })} /></Field></div>
      <div className="row"><Btn onClick={create} disabled={f.name.length < 2}>{t("common.save")}</Btn><Btn variant="ghost" onClick={() => setAdd(false)}>{t("common.cancel")}</Btn></div></Modal>}
  </>);
}
