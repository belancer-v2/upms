"use client";
import { Card, Chip, PageHead } from "@/components/ui";
import { Toggles } from "@/components/Toggles";
import { ProfilePanel } from "@/components/ProfilePanel";
import { SessionsPanel } from "@/components/SessionsPanel";
import { AccountDeletion } from "@/components/AccountDeletion";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

export default function Profile() {
  const { t, pick } = useT(); const { user, properties } = useAuth();
  if (!user) return null;
  return (<><PageHead helpKey="profile-language" title={t("profile.title")} />
    <div className="grid g2">
      <Card><dl className="kv"><dt>{t("common.name")}</dt><dd>{pick(user.name, user.name_bn)}</dd><dt>{t("auth.email")}</dt><dd>{user.email}</dd><dt>{t("unit.person.phone")}</dt><dd>{user.phone}</dd></dl></Card>
      <Card style={{ gridColumn: "1 / -1" }}><ProfilePanel kind="user" id={user.id} /></Card>
      <Card><h3>{t("profile.language")} / {t("profile.theme")}</h3><div style={{ marginTop: 14 }}><Toggles /></div></Card>
      <Card style={{ gridColumn: "1 / -1" }}><SessionsPanel /></Card>
      <Card style={{ gridColumn: "1 / -1" }}>
        <h3>{t("shell.building")}</h3>
        {properties.map((p) => <div key={p.id} className="row between" style={{ padding: "10px 0", borderTop: "1px solid var(--line)", marginTop: 8 }}><b>{pick(p.name, p.name_bn)}</b><div className="role-chips">{p.roles.map((r) => <Chip key={r}>{t(`role.${r}`)}</Chip>)}</div></div>)}
      </Card>
      <AccountDeletion />
    </div></>);
}
