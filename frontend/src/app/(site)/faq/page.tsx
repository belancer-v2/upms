"use client";
import Link from "next/link";
import { useT } from "@/lib/i18n";

export default function FaqPage() {
  const { t } = useT();
  const old = [1, 2, 3, 4, 5, 6, 7, 8].map((i) => [t(`site.faq.${i}.q`), t(`site.faq.${i}.a`)]);
  const added = [9, 10, 11, 12, 13, 14, 15].map((i) => [t(`s2.faq.${i}.q`), t(`s2.faq.${i}.a`)]);
  return (
    <section className="section"><div className="wrap-x" style={{ maxWidth: 900 }}>
      <div className="sec-head"><div className="eyebrow">{t("site.faq.eyebrow")}</div><h2>{t("s2.faq.title")}</h2><p>{t("s2.faq.sub")}</p></div>
      <div className="faq">{[...old, ...added].map(([q, a], i) => <details key={i}><summary>{q}</summary><p>{a}</p></details>)}</div>
      <p style={{ marginTop: 28 }}>{t("s2.faq.more")} <Link href="/contact">{t("s2.nav.contact")}</Link> · <Link href="/help">{t("s2.nav.help")}</Link></p>
    </div></section>
  );
}
