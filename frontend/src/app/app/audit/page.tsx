"use client";
import { useEffect, useState } from "react";
import { DataTable, PageHead } from "@/components/ui";
import { api, ftime } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { actionLabel, entityLabel } from "@/lib/act";
import { useT } from "@/lib/i18n";

type Log = { id: number; at: string; who: string; action: string; entity: string; entity_id: string };

export default function Audit() {
  const { t } = useT(); const { prop } = useAuth();
  const [rows, setRows] = useState<Log[]>([]);
  useEffect(() => { api<Log[]>("/audit?limit=200").then(setRows).catch(() => {}); }, [prop?.id]);
  return (<><PageHead helpKey="audit-log" title={t("audit.title")} sub={t("audit.sub")} />
    <DataTable rows={rows} search={(r) => `${r.who} ${r.action} ${actionLabel(t, r.action)} ${r.entity}`} cols={[
      { key: "at", head: t("audit.when"), render: (r) => <span className="nowrap">{ftime(r.at)}</span> },
      { key: "who", head: t("audit.who") },
      { key: "action", head: t("audit.what"), render: (r) => actionLabel(t, r.action) },
      { key: "entity", head: "#", render: (r) => r.entity ? `${entityLabel(t, r.entity)} ${r.entity_id}` : "" },
    ]} /></>);
}
