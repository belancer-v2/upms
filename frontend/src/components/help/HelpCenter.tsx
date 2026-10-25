"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import "./help.css";
import { Ph } from "../Placeholder";
import { Card, Chip, PageHead } from "../ui";
import { useAuth } from "@/lib/auth";
import { COMPANY } from "@/lib/company";
import { ARTICLES, groupsOf, inGroup, type Article } from "@/lib/help";
import { recommended, searchArticles } from "@/lib/help/search";
import { useT } from "@/lib/i18n";

export type Mode = "app" | "public";

export function ArticleCard({ a, base }: { a: Article; base: string }) {
  const { lang } = useT();
  return <Link href={`${base}/${a.id}`} className="hc-card"><b>{a.title[lang]}</b><span>{a.summary[lang]}</span></Link>;
}

export function ContactCard() {
  const { t, lang } = useT();
  return (
    <Card style={{ marginTop: 34 }}>
      <h3>{t("hc.contact.title")}</h3>
      <p className="muted" style={{ marginTop: 6 }}>{t("hc.contact.body")}</p>
      <div className="grid g3" style={{ marginTop: 10 }}>
        <div><div className="small muted">{t("hc.contact.email")}</div><b><Ph text={COMPANY.supportEmail[lang]} /></b></div>
        <div><div className="small muted">{t("hc.contact.phone")}</div><b><Ph text={COMPANY.supportPhone[lang]} /></b></div>
        <div><div className="small muted">{t("hc.contact.hours")}</div><b><Ph text={COMPANY.supportHours[lang]} /></b></div>
      </div>
      <p style={{ marginTop: 14 }}><Link className="btn btn-outline btn-sm" href="/contact">{t("hc.contact.form")}</Link></p>
    </Card>
  );
}

export function HelpCenter({ mode }: { mode: Mode }) {
  const { t } = useT();
  const { user, prop, roles, feature } = useAuth();
  const base = mode === "app" ? "/app/help" : "/help";
  const [q, setQ] = useState("");
  const pool = useMemo(() => (mode === "public" ? ARTICLES.filter((a) => a.public !== false) : ARTICLES.filter((a) => user?.saas_role || !a.roles.every((r) => ["SUPER_ADMIN", "SAAS_ADMIN", "SAAS_FINANCE", "SAAS_SALES", "SAAS_USER"].includes(r)))), [mode, user?.saas_role]);
  const found = useMemo(() => (q.trim() ? searchArticles(pool, q) : null), [pool, q]);
  const rec = useMemo(() => (user && mode === "app" ? recommended(pool, roles, user.saas_role, feature) : []), [pool, user, roles, feature, mode]);
  const body = (
    <>
      <div className="hc-search" role="search">
        <svg viewBox="0 0 24 24" aria-hidden><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
        <input className="input" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("hc.search")} aria-label={t("hc.search")} />
      </div>
      {found ? (
        <div style={{ marginTop: 24 }}>
          <p className="small muted">{t("hc.results", { n: found.length })} · <button className="btn btn-ghost btn-sm" onClick={() => setQ("")}>{t("hc.clear")}</button></p>
          {found.length ? <div className="hc-grid">{found.map((a) => <ArticleCard key={a.id} a={a} base={base} />)}</div> : <p className="muted">{t("hc.none")}</p>}
        </div>
      ) : (
        <div style={{ marginTop: 28 }}>
          {mode === "app" && rec.length > 0 && (
            <section className="hc-group"><h2>{t("hc.rec")}</h2><p className="small muted" style={{ marginTop: -8, marginBottom: 12 }}>{t("hc.rec_sub")}{prop ? ` · ${prop.name}` : ""}</p>
              <div className="hc-grid">{rec.map((a) => <ArticleCard key={a.id} a={a} base={base} />)}</div></section>
          )}
          {mode === "public" && !user && <p className="small muted">{t("hc.signin_hint")} {t("hc.public_note")}</p>}
          <h2 style={{ margin: "30px 0 16px", fontSize: 22 }}>{t("hc.all")} <Chip tone="mute">{pool.length}</Chip></h2>
          {groupsOf(pool).map((g) => (
            <section className="hc-group" key={g}><h2>{t(`hc.group.${g}`)}</h2>
              <div className="hc-grid">{inGroup(g, pool).map((a) => <ArticleCard key={a.id} a={a} base={base} />)}</div></section>
          ))}
        </div>
      )}
      <ContactCard />
    </>
  );
  return mode === "app"
    ? <><PageHead title={t("hc.title")} sub={t("hc.sub")} />{body}</>
    : <section className="section"><div className="wrap-x"><div className="sec-head"><div className="eyebrow">{t("site.nav.help")}</div><h2>{t("hc.title")}</h2><p>{t("hc.sub")}</p></div>{body}</div></section>;
}
