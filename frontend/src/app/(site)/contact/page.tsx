"use client";
import Link from "next/link";
import { LeadForm } from "@/components/site/LeadForm";
import { Ph } from "@/components/Placeholder";
import { Card } from "@/components/ui";
import { COMPANY } from "@/lib/company";
import { useT } from "@/lib/i18n";

export default function Contact() {
  const { t, lang } = useT();
  const row = (label: string, v: string) => <div><div className="small muted">{label}</div><b><Ph text={v} /></b></div>;
  return (
    <section className="section"><div className="wrap-x">
      <div className="sec-head"><div className="eyebrow">{t("s2.nav.contact")}</div><h2>{t("s2.contact.title")}</h2><p>{t("s2.contact.sub")}</p></div>
      <div className="grid g2" style={{ alignItems: "start" }}>
        <div><h3 style={{ marginBottom: 12 }}>{t("s2.contact.form")}</h3><LeadForm source="contact" doneKey="s2.contact.done" errKey="s2.contact.err" msgKey="s2.contact.msg" /></div>
        <Card><h3 style={{ marginBottom: 14 }}>{t("s2.contact.details")}</h3>
          <div className="stack">{row(t("s2.contact.company"), COMPANY.legalName[lang])}{row(t("s2.contact.address"), COMPANY.address[lang])}{row(t("s2.contact.email"), COMPANY.supportEmail[lang])}{row(t("s2.contact.phone"), COMPANY.supportPhone[lang])}{row(t("s2.contact.hours"), COMPANY.supportHours[lang])}</div>
          <p className="small muted" style={{ marginTop: 18 }}>{t("s2.contact.help")} <Link href="/help">{t("s2.nav.help")}</Link></p></Card>
      </div>
    </div></section>
  );
}
