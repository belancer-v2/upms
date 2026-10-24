"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Card, Chip, PageHead } from "@/components/ui";
import { DutyStrip } from "@/components/DutyStrip";
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
  if (!user) return null;
  const mine = [...(user.saas_role ? [user.saas_role] : []), ...roles];
  const modules = Array.from(new Set(mine.flatMap((r) => ROLE_MODULES[r] ?? [])));
  return (
    <>
      <PageHead eyebrow={user.saas_role ? t("dash.saas_staff") : prop ? `${t("dash.building")} ${pick(prop.name, prop.name_bn)}` : ""} title={t("dash.hello", { name: pick(user.name, user.name_bn).split(" ")[0] })} sub={prop ? [prop.org_name, prop.city].filter(Boolean).join(" · ") : t("dash.no_building")} />
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
            <ul className="list-dot" style={{ marginTop: 10 }}>{log.map((l) => <li key={l.id}><span><b>{l.who}</b> · {l.action} <span className="muted small">· {ftime(l.at)}</span></span></li>)}</ul>
          )}
        </Card>
      </div>
    </>
  );
}
