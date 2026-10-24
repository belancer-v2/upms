"use client";
import { useEffect, useState } from "react";
import { Btn, Card, Field, PageHead, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

export default function Building() {
  const { t } = useT(); const { prop, reload } = useAuth(); const toast = useToast();
  const [f, setF] = useState({ name: "", name_bn: "", address: "", city: "", floors: 0 });
  useEffect(() => { api("/property").then((p) => setF({ name: p.name, name_bn: p.name_bn, address: p.address, city: p.city, floors: p.floors })); }, [prop?.id]);
  const save = async () => { await api("/property", { method: "PUT", body: f }); await reload(); toast.show(t("building.saved")); };
  return (<><PageHead title={t("building.title")} sub={t("building.sub")} />
    <Card style={{ maxWidth: 720 }}>
      <div className="grid g2"><Field label={t("building.name")}><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field><Field label={t("building.name_bn")}><input className="input" value={f.name_bn} onChange={(e) => setF({ ...f, name_bn: e.target.value })} /></Field></div>
      <Field label={t("building.address")}><input className="input" value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} /></Field>
      <div className="grid g2"><Field label={t("port.city")}><input className="input" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} /></Field><Field label={t("port.floors")}><input className="input" type="number" value={f.floors} onChange={(e) => setF({ ...f, floors: +e.target.value })} /></Field></div>
      <Btn onClick={save}>{t("common.save")}</Btn></Card>{toast.node}</>);
}
