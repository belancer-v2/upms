"use client";
import { useEffect, useState } from "react";
import { Btn, Card, Chip, DataTable, Field, PageHead, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type Sw = { unit_id: number; number: string; enabled: boolean };
/** Manager's view of the owner rental-records add-on: only on or off per flat, never the records themselves. */
function RentalSwitches() {
  const { t } = useT(); const { prop } = useAuth(); const toast = useToast(); const [rows, setRows] = useState<Sw[] | null>(null);
  const load = () => api<Sw[]>("/rental/switches").then(setRows).catch(() => setRows([]));
  useEffect(() => { load(); }, [prop?.id]);
  const flip = async (r: Sw) => {
    if (r.enabled && !confirm(t("rent.admin.off_confirm", { n: r.number }))) return;
    try { await api(`/rental/units/${r.unit_id}/switch`, { method: "PUT", body: { enabled: !r.enabled } }); toast.show(t("rent.switched")); load(); } catch (e: any) { toast.show(e.message); }
  };
  return (<Card style={{ marginTop: 20 }}>
    <h3 style={{ marginTop: 0 }}>{t("rent.admin.title")}</h3><p className="small muted">{t("rent.admin.sub")}</p>
    {rows && <p className="small"><Chip tone="ok">{t("rent.admin.count", { n: rows.filter((r) => r.enabled).length, m: rows.length })}</Chip></p>}
    <DataTable rows={(rows ?? []).map((r) => ({ ...r, id: r.unit_id }))} pageSize={8} search={(r) => r.number} cols={[
      { key: "n", head: t("unit.number"), render: (r) => <b>{r.number}</b> },
      { key: "s", head: t("common.status"), render: (r) => <Chip tone={r.enabled ? "ok" : "mute"}>{t(r.enabled ? "rent.switch_on" : "rent.switch_off")}</Chip> },
      { key: "a", head: "", render: (r) => <Btn size="sm" variant={r.enabled ? "outline" : "soft"} onClick={() => flip(r)}>{t(r.enabled ? "rent.turn_off" : "rent.turn_on")}</Btn> }]} />
    {toast.node}
  </Card>);
}

export default function Building() {
  const { t } = useT(); const { prop, reload, feature } = useAuth(); const toast = useToast();
  const [f, setF] = useState({ name: "", name_bn: "", address: "", city: "", floors: 0 });
  useEffect(() => { api("/property").then((p) => setF({ name: p.name, name_bn: p.name_bn, address: p.address, city: p.city, floors: p.floors })); }, [prop?.id]);
  const save = async () => { await api("/property", { method: "PUT", body: f }); await reload(); toast.show(t("building.saved")); };
  return (<><PageHead helpKey="building-details" title={t("building.title")} sub={t("building.sub")} />
    <Card style={{ maxWidth: 720 }}>
      <div className="grid g2"><Field label={t("building.name")}><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field><Field label={t("building.name_bn")}><input className="input" value={f.name_bn} onChange={(e) => setF({ ...f, name_bn: e.target.value })} /></Field></div>
      <Field label={t("building.address")}><input className="input" value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} /></Field>
      <div className="grid g2"><Field label={t("port.city")}><input className="input" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} /></Field><Field label={t("port.floors")}><input className="input" type="number" value={f.floors} onChange={(e) => setF({ ...f, floors: +e.target.value })} /></Field></div>
      <Btn onClick={save}>{t("common.save")}</Btn></Card>{feature("rental_records") && <div style={{ maxWidth: 720 }}><RentalSwitches /></div>}{toast.node}</>);
}
