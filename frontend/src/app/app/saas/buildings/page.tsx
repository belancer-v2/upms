"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { DataTable, PageHead, Tabs } from "@/components/ui";
import { SubChip, daysLeft } from "@/components/saasbits";
import { api, money } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Org = { id: number; name: string; name_bn: string; city: string; plan: string; band: string; flats: number; sub_status: string; mrr: number; sms_balance: number; trial_ends: string | null; users: number };

export default function Buildings() {
  const { t, pick } = useT(); const router = useRouter();
  const [rows, setRows] = useState<Org[]>([]); const [f, setF] = useState("all");
  useEffect(() => { api<Org[]>("/saas/orgs").then(setRows); }, []);
  const view = f === "all" ? rows : rows.filter((r) => r.sub_status === f);
  return (
    <>
      <PageHead title={t("saas.b.title")} sub={t("saas.b.sub")} />
      <div style={{ marginBottom: 16 }}><Tabs value={f} onChange={setF} items={[{ id: "all", label: `${t("common.all")} · ${rows.length}` }, ...["active", "trial", "past_due", "suspended"].map((s) => ({ id: s, label: `${t(`sub.${s}`)} · ${rows.filter((r) => r.sub_status === s).length}` }))]} /></div>
      <DataTable rows={view} onRow={(r) => router.push(`/app/saas/buildings/${r.id}`)} search={(r) => `${r.name} ${r.city} ${r.plan}`} cols={[
        { key: "name", head: t("saas.b.building"), render: (r) => <b>{pick(r.name, r.name_bn)}</b> },
        { key: "city", head: t("saas.b.city") },
        { key: "plan", head: t("saas.b.plan"), render: (r) => <span style={{ textTransform: "capitalize" }}>{r.plan} · {r.band}</span> },
        { key: "flats", head: t("saas.b.flats"), num: true },
        { key: "sub_status", head: t("common.status"), render: (r) => <><SubChip s={r.sub_status} />{r.sub_status === "trial" && r.trial_ends && <span className="small muted"> {t("saas.days_left", { n: Math.max(0, daysLeft(r.trial_ends)) })}</span>}</> },
        { key: "mrr", head: t("saas.b.mrr"), num: true, render: (r) => (r.mrr ? money(r.mrr) : "–") },
        { key: "sms", head: t("saas.b.sms"), num: true, render: (r) => <span style={{ color: r.sms_balance < 100 && r.sub_status !== "suspended" ? "var(--bad)" : undefined, fontWeight: 700 }}>{r.sms_balance}</span> },
      ]} />
    </>
  );
}
