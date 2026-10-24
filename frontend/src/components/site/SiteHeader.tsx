"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Logo } from "@/components/Logo";
import { Toggles } from "@/components/Toggles";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

export function SiteHeader() {
  const { t } = useT(); const { user } = useAuth(); const path = usePathname();
  const L = ({ href, k }: { href: string; k: string }) => <Link href={href} className={path === href ? "on" : ""}>{t(k)}</Link>;
  return (
    <header className="site-header"><div className="in">
      <Link href="/" aria-label="FlatWise"><Logo height={32} /></Link>
      <nav className="site-nav"><L href="/features" k="site.nav.features" /><L href="/pricing" k="site.nav.pricing" /><L href="/demo" k="site.nav.demo" /></nav>
      <div style={{ flex: 1 }} />
      <Toggles />
      {user ? <Link className="btn btn-primary" href="/app">{t("nav.dashboard")}</Link> : <>
        <Link className="btn btn-ghost" href="/login">{t("site.nav.signin")}</Link>
        <Link className="btn btn-primary" href="/signup">{t("site.nav.trial")}</Link></>}
    </div></header>
  );
}
