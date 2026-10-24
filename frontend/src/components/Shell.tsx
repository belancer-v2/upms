"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import { ICONS, NAV } from "@/lib/nav";
import { Avatar } from "./Avatar";
import { Logo } from "./Logo";
import { Toggles } from "./Toggles";

const GROUPS = ["main", "saas", "building", "money", "people", "comms", "system"];

export function Icon({ name }: { name: string }) { return <svg viewBox="0 0 24 24" aria-hidden><path d={ICONS[name] ?? ICONS.home} /></svg>; }

export function Shell({ children }: { children: ReactNode }) {
  const { ready, user, properties, prop, setProp, has, saas, logout, feature } = useAuth();
  const { t, pick } = useT();
  const path = usePathname(); const router = useRouter();
  const [open, setOpen] = useState(false);
  useEffect(() => { if (ready && !user) router.replace("/login"); }, [ready, user, router]);
  useEffect(() => setOpen(false), [path]);
  if (!ready || !user) return <div className="empty" style={{ paddingTop: 120 }}>{t("common.loading")}</div>;

  const hrefs = NAV.map((i) => i.href);
  const isOn = (h: string) => path === h || (h !== "/app" && path.startsWith(h + "/") && !hrefs.some((o) => o.length > h.length && (path === o || path.startsWith(o + "/"))));
  const visible = NAV.filter((i) => i.anyone || (i.roles && prop && has(...i.roles) && (!i.feature || feature(i.feature))) || (i.saas && saas(...i.saas)));
  return (
    <div className="shell">
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand"><Link href="/app"><Logo /></Link></div>
        <nav className="nav">
          {GROUPS.map((g) => {
            const items = visible.filter((i) => i.group === g);
            if (!items.length) return null;
            return (
              <div className="nav-group" key={g}>
                <div className="nav-title">{t(`nav.group.${g}`)}</div>
                {items.map((i) => <Link key={i.href} href={i.href} className={isOn(i.href) ? "on" : ""}><Icon name={i.icon} />{t(i.key)}</Link>)}
              </div>
            );
          })}
        </nav>
      </aside>
      <div className="main">
        <header className="topbar">
          <button className="icon-btn menu-btn" aria-label="Menu" onClick={() => setOpen(!open)}><svg viewBox="0 0 24 24"><path d="M3 6h18M3 12h18M3 18h18" /></svg></button>
          {properties.length > 0 && !path.startsWith("/app/saas") && (
            <div className="row" style={{ gap: 8 }}>
              <span className="small muted">{t("shell.building")}</span>
              {properties.length > 1
                ? <select className="input" style={{ width: 230, minHeight: 40, padding: "6px 12px" }} value={prop?.id ?? 0} onChange={(e) => { setProp(Number(e.target.value)); window.location.reload(); }} aria-label={t("shell.building")}>
                    {properties.map((p) => <option key={p.id} value={p.id}>{pick(p.name, p.name_bn)}</option>)}</select>
                : <b>{pick(prop?.name, prop?.name_bn)}</b>}
            </div>
          )}
          <div className="grow" />
          <Toggles />
          <div className="row" style={{ gap: 10 }}>
            <Avatar kind="user" id={user.id} name={pick(user.name, user.name_bn)} size={38} />
            <div className="small" style={{ lineHeight: 1.2 }}><b>{pick(user.name, user.name_bn)}</b><br /><span className="muted">{user.saas_role ? t(`role.${user.saas_role}`) : ""}</span></div>
            <button className="btn btn-ghost btn-sm" onClick={logout}>{t("auth.signout")}</button>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
