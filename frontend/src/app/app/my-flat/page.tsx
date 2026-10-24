"use client";
import { useCallback, useEffect, useState } from "react";
import { StatusChip, UnitPanel, PersonLine, type Unit } from "@/components/UnitParts";
import { Btn, Card, PageHead, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

export default function MyFlat() {
  const { t } = useT(); const { prop } = useAuth(); const toast = useToast();
  const [units, setUnits] = useState<Unit[] | null>(null); const [open, setOpen] = useState<Unit | null>(null);
  const load = useCallback(() => api<Unit[]>("/units").then(setUnits), []);
  useEffect(() => { load(); }, [load, prop?.id]);
  if (!units) return <p className="muted">{t("common.loading")}</p>;
  return (<>
    <PageHead title={t("myflat.title")} sub={t("myflat.sub")} />
    {units.length === 0 && <Card><p className="muted">{t("myflat.none")}</p></Card>}
    <div className="grid g2">{units.map((u) => (
      <Card key={u.id}><div className="row between"><h2>{u.number}</h2><StatusChip s={u.status} /></div>
        <p className="small muted">{t("unit.floor", { n: u.floor })} · {u.area_sqft} sq ft · {u.bedrooms} {t("unit.beds").toLowerCase()}</p>
        <h3 style={{ margin: "14px 0 2px" }}>{t("unit.owners")}</h3>{u.owners.map((p) => <PersonLine key={p.id} p={p} showContact />)}
        <h3 style={{ margin: "14px 0 2px" }}>{t("myflat.tenant")}</h3>{u.tenants.length ? u.tenants.map((p) => <PersonLine key={p.id} p={p} showContact />) : <p className="muted small">{t("myflat.no_tenant")}</p>}
        <div style={{ marginTop: 16 }}><Btn onClick={() => setOpen(u)}>{t("common.view")}</Btn></div></Card>))}</div>
    {open && <UnitPanel unit={open} onClose={() => setOpen(null)} onChange={async (u, temp) => { await load(); setOpen(u); if (temp) toast.show(t("unit.person.temp", { pw: temp })); }} />}
    {toast.node}
  </>);
}
