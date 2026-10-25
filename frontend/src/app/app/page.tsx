"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Card, Chip, PageHead } from "@/components/ui";
import { DutyStrip } from "@/components/DutyStrip";
import { SetupCard } from "@/components/setup/SetupCard";
import { actionLabel } from "@/lib/act";
import { api, ftime } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import { ROLE_MODULES } from "@/lib/i18n/roles";

type Log = { id: number; at: string; who: string; action: string; entity: string };

export default function Dashboard() {
  const { t, pick } = useT(); const { user, prop, roles } = useAuth(); const router = useRouter();
  useEffect(() => { if (user?.saas_role) router.replace("/app/saas"); }, [user, router]);
  const [log, setLog] = useState<Log[] | null>(null);
  useEffect(() => { api<Log[]>("/audit?limit=6").then(setLog).catch(() => setLog([])); }, [prop?.id]);
  type CS = Record<"sms" | "email", { balance: number; threshold: number; is_low: boolean }>;
  const [cr, setCr] = useState<CS | null>(null); const [ended, setEnded] = useState<{ readonly: boolean; days_left: number } | null>(null);
  const buyer = !!prop && roles.some((r) => ["PROPERTY_ADMIN", "AGENCY_MANAGER", "TREASURER", "PRESIDENT"].includes(r));
  const manager = !!prop && roles.some((r) => ["PROPERTY_ADMIN", "AGENCY_MANAGER"].includes(r));
  useEffect(() => { setCr(null); if (buyer) api<CS>("/credits/summary").then(setCr).catch(() => setCr(null)); }, [buyer, prop?.id]);
  useEffect(() => { setEnded(null); if (manager && prop?.sub_status === "cancelled") api<{ cancelled: { readonly: boolean; days_left: number } | null }>("/plan").then((p) => setEnded(p.cancelled)).catch(() => setEnded(null)); }, [manager, prop?.id, prop?.sub_status]);
  const [ctr, setCtr] = useState<{ renewal: number; expired: number; visit_overdue: number } | null>(null);
  const watcher = !!prop && roles.some((r) => ["PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY", "TREASURER", "MEMBER", "AUDITOR", "CARETAKER"].includes(r)) && prop.features.includes("maintenance");
  useEffect(() => { setCtr(null); if (watcher) api<{ renewal: number; expired: number; visit_overdue: number }>("/contracts/summary").then(setCtr).catch(() => setCtr(null)); }, [watcher, prop?.id]);
  if (!user) return null;
  const lows = cr ? (["sms", "email"] as const).filter((k) => cr[k].is_low) : [];
  const mine = [...(user.saas_role ? [user.saas_role] : []), ...roles];
  const modules = Array.from(new Set(mine.flatMap((r) => ROLE_MODULES[r] ?? [])));
  return (
    <>
      <PageHead helpKey="getting-started" eyebrow={user.saas_role ? t("dash.saas_staff") : prop ? `${t("dash.building")} ${pick(prop.name, prop.name_bn)}` : ""} title={t("dash.hello", { name: pick(user.name, user.name_bn).split(" ")[0] })} sub={prop ? [prop.org_name, prop.city].filter(Boolean).join(" · ") : t("dash.no_building")} />
      {ended && <div role="alert" className="card" style={{ marginBottom: 12, borderColor: "var(--bad)", fontWeight: 700 }}>{ended.readonly ? t("plan.ended_ro") : t("plan.ended_grace", { n: ended.days_left })} <Link href="/app/plan" className="btn btn-soft btn-sm" style={{ marginInlineStart: 8 }}>{t("plan.open")}</Link></div>}
      {ctr && (ctr.renewal + ctr.expired + ctr.visit_overdue > 0) && <div role="alert" className="card" style={{ marginBottom: 12, borderColor: "var(--warn)", background: "var(--warn-bg)", color: "var(--warn)", fontWeight: 700 }}>
        {t("dash.contracts", { r: ctr.renewal + ctr.expired, v: ctr.visit_overdue })} <Link href="/app/contracts" className="btn btn-soft btn-sm" style={{ marginInlineStart: 8 }}>{t("dash.contracts_open")}</Link></div>}
      {lows.map((k) => <div key={k} role="alert" className="card" style={{ marginBottom: 12, borderColor: "var(--warn)", background: "var(--warn-bg)", color: "var(--warn)", fontWeight: 700 }}>
        {t("dash.low", { k: t(`cr.${k}`), n: cr![k].balance.toLocaleString("en-US"), t: cr![k].threshold.toLocaleString("en-US") })} <Link href="/app/credits" className="btn btn-soft btn-sm" style={{ marginInlineStart: 8 }}>{t("dash.topup")}</Link></div>)}
      <SetupCard />
      <div className="grid g2">
        <Card>
          <h3>{user.saas_role && roles.length === 0 ? t("dash.saas_staff") : t("shell.roles_here")}</h3>
          <div className="role-chips" style={{ margin: "12px 0 16px" }}>{mine.map((r) => <Chip key={r}>{t(`role.${r}`)}</Chip>)}</div>
          {mine.slice(0, 3).map((r) => <p key={r} className="small muted" style={{ margin: "0 0 6px" }}><b style={{ color: "var(--text)" }}>{t(`role.${r}`)}</b> · {t(`roles.desc.${r}`)}</p>)}
        </Card>
        <Card>
          <h3>{t("dash.workspace")}</h3>
          <div className="row wrap" style={{ gap: 8, marginTop: 12 }}>{modules.map((m) => <Chip key={m} tone="info">{t(`mod.${m}`)}</Chip>)}</div>
        </Card>
        {roles.some((r) => ["FLAT_OWNER", "TENANT", "OWNER_REP"].includes(r)) && <DutyStrip />}
        <Card style={{ gridColumn: "1 / -1" }}>
          <h3>{t("dash.recent")}</h3>
          {log === null ? <p className="muted">{t("common.loading")}</p> : log.length === 0 ? <p className="muted">{t("dash.nothing")}</p> : (
            <ul className="list-dot" style={{ marginTop: 10 }}>{log.map((l) => <li key={l.id}><span><b>{l.who}</b> · {actionLabel(t, l.action)} <span className="muted small">· {ftime(l.at)}</span></span></li>)}</ul>
          )}
        </Card>
      </div>
    </>
  );
}
