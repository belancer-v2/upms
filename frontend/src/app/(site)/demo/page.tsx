"use client";
import { LeadForm } from "@/components/site/LeadForm";
import { useT } from "@/lib/i18n";

export default function Demo() {
  const { t } = useT();
  return (
    <section className="section"><div className="wrap-x" style={{ maxWidth: 720 }}>
      <div className="sec-head"><div className="eyebrow">{t("site.nav.demo")}</div><h2>{t("site.demo.title")}</h2><p>{t("site.demo.sub")}</p></div>
      <LeadForm source="demo" doneKey="site.demo.done" errKey="site.demo.err" msgKey="site.demo.msg" sendKey="site.demo.send" />
    </div></section>
  );
}
