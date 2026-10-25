"use client";
import Link from "next/link";
import { useState } from "react";
import { Icon } from "@/components/Shell";
import { Bar, Chip, Tabs } from "@/components/ui";
import { Faq, PricingCards } from "@/components/site/Pricing";
import { useT } from "@/lib/i18n";

const MODULES: [string, string][] = [["billing", "receipt"], ["cash", "cash"], ["finance", "chart"], ["assets", "box"], ["staff", "users"], ["notices", "megaphone"], ["tenant", "file"], ["complaints", "wrench"], ["committee", "gavel"], ["reports", "list"]];

function HeroMock() {
  const { t } = useT();
  return (
    <div className="mock" aria-hidden>
      <div className="col" style={{ gap: 14 }}>
        <div className="card"><div className="small muted">{t("site.mock.collect")}</div><div className="big">BDT 186,000</div><div style={{ margin: "12px 0 6px" }}><Bar pct={62} spark /></div><div className="small muted">{t("site.mock.of")}</div></div>
        <div className="card"><div className="note"><span className="sq" /><div><b>{t("site.mock.ready")}</b><br /><span className="small muted">BDT 4,500 · 9 Oct</span></div></div>
          <div className="note" style={{ marginTop: 8 }}><span className="sq" /><b>{t("site.mock.notice")}</b></div>
          <div className="note" style={{ marginTop: 8 }}><span className="sq r" /><span className="muted">{t("site.mock.due")}</span></div></div>
      </div>
      <div className="phone"><div className="top">{t("site.mock.today")}</div><div className="body">
        <span className="btn btn-primary">{t("site.mock.record")}</span><span className="btn btn-outline">{t("site.mock.meter")}</span><Chip tone="info">{t("site.mock.sync")}</Chip>
        <div className="note"><Chip tone="ok">{t("site.mock.paid")}</Chip><span className="small">{t("site.mock.unit", { n: "B-302" })}</span></div><div className="note"><Chip tone="warn">{t("site.mock.duechip")}</Chip><span className="small">{t("site.mock.unit", { n: "A-501" })}</span></div></div></div>
    </div>
  );
}

export default function Home() {
  const { t } = useT(); const [u, setU] = useState("committee");
  return (
    <>
      <section className="hero"><div className="wrap-x hero-grid">
        <div>
          <div className="eyebrow">{t("site.hero.eyebrow")}</div>
          <h1>{t("site.hero.title").replace(/[.।]$/, "")}<span className="dot">{t("site.hero.title").slice(-1)}</span></h1>
          <p className="lead">{t("site.hero.sub")}</p>
          <div className="row wrap" style={{ marginTop: 28, gap: 14 }}><Link className="btn btn-primary btn-lg" href="/signup">{t("site.hero.cta1")}</Link><Link className="btn btn-ghost btn-lg" href="/demo">{t("site.hero.cta2")}</Link></div>
          <div className="trust">{[1, 2, 3, 4].map((i) => <span key={i}>{t(`site.trust.${i}`)}</span>)}</div>
        </div>
        <HeroMock />
      </div></section>

      <section className="section alt"><div className="wrap-x">
        <div className="sec-head"><div className="eyebrow">{t("site.why.eyebrow")}</div><h2>{t("site.why.title")}</h2></div>
        <div className="grid g3">{[1, 2, 3, 4, 5, 6].map((i) => <div key={i} className="card"><h3>{t(`site.why.${i}.t`)}</h3><p className="muted" style={{ marginTop: 8 }}>{t(`site.why.${i}.d`)}</p></div>)}</div>
      </div></section>

      <section className="section" id="features"><div className="wrap-x">
        <div className="sec-head"><div className="eyebrow">{t("site.feat.eyebrow")}</div><h2>{t("site.feat.title")}</h2><p>{t("site.feat.sub")}</p></div>
        <div className="grid g4" style={{ gap: 22 }}>{MODULES.map(([k, ic]) => <div key={k} className="card feature"><div className="ic"><Icon name={ic} /></div><h3>{t(`site.m.${k}`)}</h3><p>{t(`site.m.${k}.d`)}</p></div>)}</div>
      </div></section>

      <section className="section alt"><div className="wrap-x">
        <div className="sec-head"><div className="eyebrow">{t("site.users.eyebrow")}</div><h2>{t("site.users.title")}</h2></div>
        <Tabs value={u} onChange={setU} items={["committee", "owner", "caretaker", "agency"].map((k) => ({ id: k, label: t(`site.u.${k}`) }))} />
        <div className="grid g2" style={{ marginTop: 22, alignItems: "stretch" }}>
          <div className="card"><ul className="list-dot" style={{ fontSize: 20, fontWeight: 700 }}>{[1, 2, 3].map((i) => <li key={i}>{t(`site.u.${u}.${i}`)}</li>)}</ul></div>
          <div className="card card-hero" style={{ minHeight: 190, display: "flex", alignItems: "flex-end" }}><h2>{t(`site.u.${u}`)}</h2></div>
        </div>
      </div></section>

      <section className="section"><div className="wrap-x">
        <div className="sec-head"><div className="eyebrow">{t("site.how.eyebrow")}</div><h2>{t("site.how.title")}</h2></div>
        <div className="grid g4">{[1, 2, 3, 4].map((i) => <div key={i} className="card"><div className="eyebrow">0{i}</div><h3 style={{ margin: "8px 0" }}>{t(`site.how.${i}.t`)}</h3><p className="muted">{t(`site.how.${i}.d`)}</p></div>)}</div>
      </div></section>

      <section className="section alt" id="pricing"><div className="wrap-x">
        <div className="sec-head"><div className="eyebrow">{t("site.price.eyebrow")}</div><h2>{t("site.price.title")}</h2><p>{t("site.price.sub")}</p></div>
        <PricingCards compact />
        <p style={{ marginTop: 22 }}><Link href="/pricing" className="btn btn-soft">{t("site.price.compare")} →</Link></p>
      </div></section>

      <section className="section" id="faq"><div className="wrap-x" style={{ maxWidth: 900 }}>
        <div className="sec-head"><div className="eyebrow">{t("site.faq.eyebrow")}</div><h2>{t("site.faq.title")}</h2></div>
        <Faq />
      </div></section>

      <section className="wrap-x"><div className="cta-band"><div><h2>{t("site.cta.title")}</h2><p>{t("site.cta.sub")}</p></div>
        <div className="row wrap"><Link className="btn btn-light btn-lg" href="/signup">{t("site.hero.cta1")}</Link><Link className="btn btn-lg" style={{ border: "2px solid #F1B8D3", color: "#fff" }} href="/demo">{t("site.hero.cta2")}</Link></div></div></section>
    </>
  );
}
