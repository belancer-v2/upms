"use client";
import { useEffect, useState } from "react";
import { Chip, DataTable, PageHead, Tabs } from "@/components/ui";
import { api, fdate } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type P = { id: number; kind: string; name: string; name_bn: string; phone: string; unit: string; resides: boolean; has_login: boolean; since: string };
export default function People() {
  const { t, pick } = useT(); const { prop } = useAuth(); const [rows, setRows] = useState<P[]>([]); const [k, setK] = useState("");
  useEffect(() => { api<P[]>("/people").then(setRows); }, [prop?.id]);
  const view = k ? rows.filter((r) => r.kind === k) : rows;
  return (<>
    <PageHead title={t("people.title")} sub={t("people.sub")} />
    <div style={{ marginBottom: 16 }}><Tabs value={k} onChange={setK} items={[{ id: "", label: `${t("people.all")} · ${rows.length}` }, { id: "owner", label: `${t("unit.owners")} · ${rows.filter((r) => r.kind === "owner").length}` }, { id: "tenant", label: `${t("unit.tenants")} · ${rows.filter((r) => r.kind === "tenant").length}` }]} /></div>
    <DataTable rows={view} pageSize={12} search={(r) => `${r.name} ${r.unit} ${r.phone}`} cols={[
      { key: "name", head: t("common.name"), render: (r) => <b>{pick(r.name, r.name_bn)}</b> }, { key: "unit", head: t("people.flat") },
      { key: "kind", head: t("people.type"), render: (r) => <Chip tone={r.kind === "owner" ? "" : "info"}>{t(`unit.${r.kind}`)}{r.kind === "owner" ? ` · ${r.resides ? t("unit.lives") : t("unit.rented")}` : ""}</Chip> },
      { key: "phone", head: t("people.phone"), render: (r) => r.phone || "–" }, { key: "since", head: t("people.since"), render: (r) => <span className="nowrap">{fdate(r.since)}</span> },
      { key: "login", head: "", render: (r) => r.has_login ? <Chip tone="info">{t("unit.login")}</Chip> : null }]} /></>);
}
