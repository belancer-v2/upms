"use client";
import { Card, Chip, PageHead } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { CUSTOMER_LIST, ROLE_MODULES, SAAS_LIST } from "@/lib/i18n/roles";

export default function Roles() {
  const { t } = useT();
  const block = (title: string, list: string[]) => (
    <>
      <h2 style={{ margin: "26px 0 14px" }}>{title}</h2>
      <div className="grid g2">
        {list.map((r) => (
          <Card key={r}>
            <div className="row between"><h3>{t(`role.${r}`)}</h3></div>
            <p className="muted small" style={{ margin: "6px 0 12px" }}>{t(`roles.desc.${r}`)}</p>
            <div className="small muted" style={{ marginBottom: 6 }}>{t("roles.can")}</div>
            <div className="row wrap" style={{ gap: 6 }}>{ROLE_MODULES[r].map((m) => <Chip key={m} tone="info">{t(`mod.${m}`)}</Chip>)}</div>
          </Card>
        ))}
      </div>
    </>
  );
  return (<><PageHead helpKey="roles-access" title={t("roles.title")} sub={t("roles.sub")} />{block(t("roles.saas"), SAAS_LIST)}{block(t("roles.customer"), CUSTOMER_LIST)}</>);
}
