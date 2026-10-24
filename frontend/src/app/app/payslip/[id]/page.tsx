"use client";
import { use, useEffect, useState } from "react";
import { Btn, Card } from "@/components/ui";
import { Avatar } from "@/components/Avatar";
import { api, fdate, money } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type P = { staff_id: number; building: string; building_bn: string; address: string; period: string; status: string; paid_on: string | null; name: string; name_bn: string; role: string; base: number; bonus: number; bonus_kind: string; deduction: number; net: number; note: string; method: string };
export default function Payslip({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params); const { t, pick } = useT(); const { prop } = useAuth(); const [p, setP] = useState<P | null>(null); const [err, setErr] = useState("");
  useEffect(() => { api<P>(`/staff/payroll/lines/${id}/payslip`).then(setP).catch((e) => setErr(e.message)); }, [id, prop?.id]);
  if (err) return <p className="error">{err}</p>; if (!p) return <p className="muted">{t("common.loading")}</p>;
  const row = (k: string, v: React.ReactNode, strong = false) => <div className="row between" style={{ padding: "9px 0", borderTop: "1px solid var(--line)" }}><span className="muted">{k}</span>{strong ? <b style={{ fontSize: 20 }}>{v}</b> : <b>{v}</b>}</div>;
  return (<div style={{ maxWidth: 560, margin: "0 auto" }}><Card><div className="eyebrow">{t("slip.title")}</div><h2 style={{ margin: "4px 0" }}>{pick(p.building, p.building_bn || p.building)}</h2><span className="small muted">{p.address}</span>
    <div style={{ height: 14 }} />{row(t("slip.employee"), <span className="row" style={{ gap: 8 }}><Avatar kind="staff" id={p.staff_id} name={pick(p.name, p.name_bn || p.name)} size={30} />{pick(p.name, p.name_bn || p.name)}</span>)}{row(t("slip.job"), t(`staff.role.${p.role}`))}{row(t("slip.month"), p.period)}
    {row(t("pay.base"), money(p.base))}{p.bonus > 0 && row(`${t("pay.bonus")}${p.bonus_kind === "eid" ? ` (${t("pay.eid_tag")})` : ""}`, money(p.bonus))}{p.deduction > 0 && row(t("pay.deduction"), `− ${money(p.deduction)}`)}
    {row(t("pay.net"), money(p.net), true)}{row(t("slip.status"), p.paid_on ? `${t("pay.st.paid")} · ${fdate(p.paid_on)} · ${t(`fin.method.${p.method}`)}` : t("slip.not_paid"))}
    <div className="row" style={{ marginTop: 18 }}><Btn onClick={() => window.print()}>{t("common.print")}</Btn></div></Card></div>);
}
