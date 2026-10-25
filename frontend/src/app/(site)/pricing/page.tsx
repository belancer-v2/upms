"use client";
import Link from "next/link";
import { CompareTable, Faq, PricingCards, usePlans } from "@/components/site/Pricing";
import { money } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function Pricing() {
  const { t } = useT(); const plans = usePlans();
  return (
    <>
      <section className="section" style={{ paddingBottom: 30 }}><div className="wrap-x">
        <div className="sec-head"><div className="eyebrow">{t("site.price.eyebrow")}</div><h2>{t("site.price.title")}</h2><p>{t("site.price.sub")}</p></div>
        <PricingCards />
        <div className="card" style={{ marginTop: 26 }}><h3>{t("site.price.addons")}</h3><ul className="list-dot" style={{ marginTop: 10 }}>{[1, 2, 3, 4].map((i) => <li key={i}>{i === 1 && plans ? t("s2.addon.sms", { n: plans.sms_pack.count.toLocaleString("en-US"), amt: money(plans.sms_pack.price) }) : t(`site.price.addon.${i}`)}</li>)}</ul></div>
      </div></section>
      <section className="section alt"><div className="wrap-x"><h2 style={{ marginBottom: 18 }}>{t("site.price.compare")}</h2><CompareTable /></div></section>
      <section className="section" id="faq"><div className="wrap-x" style={{ maxWidth: 900 }}><div className="sec-head"><div className="eyebrow">{t("site.faq.eyebrow")}</div><h2>{t("site.faq.title")}</h2></div><Faq />
        <p style={{ marginTop: 28 }}><Link className="btn btn-primary btn-lg" href="/signup">{t("site.hero.cta1")}</Link></p></div></section>
    </>
  );
}
