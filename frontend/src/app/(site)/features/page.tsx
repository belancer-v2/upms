"use client";
import Link from "next/link";
import { Icon } from "@/components/Shell";
import { CompareTable, FEATURE_ORDER, SOON } from "@/components/site/Pricing";
import { Chip } from "@/components/ui";
import { useT } from "@/lib/i18n";

const MODS: [string, string, string[]][] = [
  ["billing", "receipt", ["billing", "reminders", "reports"]], ["cash", "cash", ["cash_confirm", "cash_otp", "caretaker_app"]], ["finance", "chart", ["expenses", "assets"]],
  ["staff", "users", ["staff"]], ["notices", "megaphone", ["notices", "policies"]], ["tenant", "file", ["tenant_dmp"]],
];
export default function Features() {
  const { t } = useT();
  return (
    <section className="section"><div className="wrap-x">
      <div className="sec-head"><div className="eyebrow">{t("site.nav.features")}</div><h2>{t("site.feats.title")}</h2><p>{t("site.feats.sub")}</p></div>
      <div className="grid g2" style={{ gap: 22 }}>
        {MODS.map(([k, ic, feats]) => (
          <div key={k} className="card feature"><div className="row"><div className="ic"><Icon name={ic} /></div><h3>{t(`site.m.${k}`)}</h3></div><p>{t(`site.m.${k}.d`)}</p>
            <ul className="feat-list">{feats.map((f) => <li key={f}>{t(`feat.${f}`)}{SOON.has(f) && <Chip tone="mute">{t("site.price.soon")}</Chip>}</li>)}</ul></div>
        ))}
      </div>
      <h2 style={{ margin: "56px 0 18px" }}>{t("site.price.compare")}</h2>
      <CompareTable />
      <p style={{ marginTop: 26 }}><Link className="btn btn-primary btn-lg" href="/signup">{t("site.hero.cta1")}</Link></p>
    </div></section>
  );
}
