"use client";
import { useEffect, useState } from "react";
import { Chip, DataTable, PageHead } from "@/components/ui";
import { api, ftime } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type M = { id: number; at: string; to: string; phone: string; unit: string; template: string; lang: string; body: string; status: string; error: string };
export default function Messages() {
  const { t } = useT(); const { prop } = useAuth(); const [rows, setRows] = useState<M[]>([]);
  useEffect(() => { api<M[]>("/billing/messages").then(setRows); }, [prop?.id]);
  return (<><PageHead title={t("msg.title")} sub={t("msg.sub")} />
    <DataTable rows={rows} pageSize={10} search={(r) => `${r.to} ${r.unit} ${r.body}`} cols={[
      { key: "at", head: t("msg.when"), render: (r) => <span className="nowrap">{ftime(r.at)}</span> }, { key: "unit", head: t("bill.flat"), render: (r) => <b>{r.unit}</b> }, { key: "to", head: t("msg.to"), render: (r) => <>{r.to}<br /><span className="small muted">{r.phone}</span></> },
      { key: "tpl", head: "", render: (r) => <Chip tone="mute">{t(`msg.tpl.${r.template}`)}</Chip> }, { key: "body", head: t("msg.text"), render: (r) => <span className="small">{r.body}</span> },
      { key: "st", head: t("common.status"), render: (r) => <Chip tone={r.status === "sent" ? "ok" : "bad"}>{t(`msg.${r.status}`)}{r.error ? ` · ${r.error}` : ""}</Chip> }]} /></>);
}
