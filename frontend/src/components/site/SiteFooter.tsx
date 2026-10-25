"use client";
import Link from "next/link";
import { Logo } from "@/components/Logo";
import { useT } from "@/lib/i18n";

export function SiteFooter() {
  const { t } = useT();
  return (
    <footer className="footer"><div className="wrap-x"><div className="cols">
      <div><Logo height={30} /><p className="muted" style={{ marginTop: 12 }}>{t("site.foot.tag")}</p></div>
      <div className="col"><b>{t("site.foot.product")}</b><Link href="/features">{t("site.nav.features")}</Link><Link href="/pricing">{t("site.nav.pricing")}</Link><Link href="/faq">{t("site.nav.faq")}</Link></div>
      <div className="col"><b>{t("site.foot.company")}</b><Link href="/signup">{t("site.nav.trial")}</Link><Link href="/demo">{t("site.nav.demo")}</Link><Link href="/login">{t("site.nav.signin")}</Link></div>
    </div>
    <p className="small" style={{ marginTop: 26, display: "flex", flexWrap: "wrap", gap: "6px 18px" }}><Link href="/faq">{t("site.nav.faq")}</Link><Link href="/help">{t("s2.nav.help")}</Link><Link href="/contact">{t("s2.nav.contact")}</Link><Link href="/terms">{t("s2.nav.terms")}</Link><Link href="/privacy">{t("s2.nav.privacy")}</Link><Link href="/refund">{t("s2.nav.refund")}</Link></p>
    <p className="small muted" style={{ marginTop: 14 }}>{t("site.foot.rights")}</p></div></footer>
  );
}
