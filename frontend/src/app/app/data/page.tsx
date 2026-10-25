"use client";
import { useEffect, useState } from "react";
import { Btn, Card, PageHead, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { downloadFile } from "@/lib/download";
import { useT } from "@/lib/i18n";

type St = { allowed_roles: string[]; per_day: number; used_today: number; left_today: number; can_export: boolean };

export default function DataExport() {
  const { t } = useT(); const { prop } = useAuth(); const toast = useToast();
  const [st, setSt] = useState<St | null>(null); const [busy, setBusy] = useState(false);
  const load = () => api<St>("/export/status").then(setSt).catch(() => setSt(null));
  useEffect(() => { load(); }, [prop?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const go = async () => {
    setBusy(true);
    try { await downloadFile("/export/building.zip", "flatwise-export.zip"); toast.show(t("dx.zip.done")); } catch (e: any) { toast.show(t("dx.failed", { e: e.message })); } finally { setBusy(false); load(); }
  };
  return (
    <>
      <PageHead helpKey="export-data" title={t("dx.title")} sub={t("dx.sub")} />
      <div className="grid g2" style={{ alignItems: "start" }}>
        <Card>
          <h3>{t("dx.zip.title")}</h3><p className="muted" style={{ marginTop: 6 }}>{t("dx.zip.body")}</p>
          {st?.can_export ? <>
            <p className="small muted">{st.left_today > 0 ? t("dx.zip.left", { n: st.left_today, m: st.per_day }) : t("dx.zip.none_left", { m: st.per_day })}</p>
            <Btn onClick={go} disabled={busy || st.left_today <= 0}>{busy ? t("dx.preparing") : t("dx.zip.go")}</Btn>
            <p className="small muted" style={{ marginTop: 12 }}>{t("dx.zip.who")}</p></> : <p className="small muted">{t("dx.zip.not_allowed")}</p>}
        </Card>
        <Card><h3>{t("dx.single.title")}</h3><p className="muted" style={{ marginTop: 6 }}>{t("dx.single.body")}</p></Card>
        <Card><h3>{t("dx.care.title")}</h3><p className="muted" style={{ marginTop: 6 }}>{t("dx.care.body")}</p></Card>
        <Card><h3>{t("dx.move.title")}</h3><p className="muted" style={{ marginTop: 6 }}>{t("dx.move.body")}</p></Card>
      </div>
      {toast.node}
    </>
  );
}
