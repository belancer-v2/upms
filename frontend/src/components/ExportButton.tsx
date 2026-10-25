"use client";
import { useState } from "react";
import { Btn, useToast } from "./ui";
import { downloadFile } from "@/lib/download";
import { useT } from "@/lib/i18n";

export type ExportName = "invoices" | "payments" | "dues" | "ledger" | "expenses" | "people" | "visitors";

/** One button that downloads a list as a CSV (UTF-8 with BOM, opens in Excel with Bangla text intact). Shared by every list page. */
export function ExportButton({ name, query = "", label }: { name: ExportName; query?: string; label?: string }) {
  const { t } = useT(); const toast = useToast(); const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    try { await downloadFile(`/export/csv/${name}${query ? `?${query}` : ""}`, `flatwise-${name}.csv`); toast.show(t("dx.downloaded")); }
    catch (e: any) { toast.show(t("dx.failed", { e: e.message })); } finally { setBusy(false); }
  };
  return <><Btn variant="outline" size="sm" onClick={go} disabled={busy} title={t("dx.csv_hint")}>{busy ? t("dx.preparing") : label ?? t("dx.csv")}</Btn>{toast.node}</>;
}
