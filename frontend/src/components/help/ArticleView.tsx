"use client";
import Link from "next/link";
import { useState } from "react";
import "./help.css";
import { ArticleCard, ContactCard } from "./HelpCenter";
import { Card, Chip, PageHead } from "../ui";
import { byId, type Article, type Shot } from "@/lib/help";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

function HelpShot({ shot }: { shot: Shot }) {
  const { t, lang } = useT();
  const [ok, setOk] = useState(true);
  return (
    <figure className="hc-shot">
      {ok /* eslint-disable-next-line @next/next/no-img-element */ ? <img src={shot.src} alt={shot.alt[lang]} loading="lazy" onError={() => setOk(false)} /> : <div className="slot">{t("hc.shot_soon")}</div>}
      <figcaption>{shot.alt[lang]}</figcaption>
    </figure>
  );
}

export function ArticleView({ id, mode }: { id: string; mode: "app" | "public" }) {
  const { t, lang } = useT();
  const { feature, user } = useAuth();
  const a: Article | undefined = byId(id);
  const base = mode === "app" ? "/app/help" : "/help";
  if (!a || (mode === "public" && a.public === false)) return <Card><p className="muted">{t("hc.notfound")}</p><Link className="btn btn-outline btn-sm" href={base}>{t("hc.back")}</Link></Card>;
  const rel = (a.related ?? []).map(byId).filter((x): x is Article => !!x && (mode === "app" || x.public !== false));
  const off = !!a.feature && !!user && !user.saas_role && !feature(a.feature);
  const head = (
    <>
      <p className="small"><Link href={base}>← {t("hc.back")}</Link></p>
      <div className="hc-roles" style={{ margin: "8px 0 14px" }} aria-label={t("hc.for")}>
        <span className="small muted">{t("hc.for")}:</span>
        {a.roles.slice(0, 6).map((r) => <Chip key={r}>{t(`role.${r}`)}</Chip>)}
        {a.roles.length > 6 && <Chip tone="mute">+{a.roles.length - 6}</Chip>}
        {off && <Chip tone="warn">{t("hc.not_in_plan")}</Chip>}
      </div>
    </>
  );
  const content = (
    <div className="hc-article stack">
      <p style={{ fontSize: 18 }}>{a.summary[lang]}</p>
      {a.shots?.map((s) => <HelpShot key={s.src} shot={s} />)}
      <Card><h3 style={{ marginBottom: 8 }}>{t("hc.steps")}</h3><ol>{a.steps[lang].map((s, i) => <li key={i}><span>{s}</span></li>)}</ol></Card>
      <div><h3 style={{ marginBottom: 10 }}>{t("hc.tips")}</h3>{a.tips[lang].map((s, i) => <div className="hc-tip" key={i}>{s}</div>)}</div>
      {mode === "app" && a.route && <p><Link className="btn btn-primary" href={a.route}>{t("hc.open")}</Link></p>}
      {rel.length > 0 && <div><h3 style={{ marginBottom: 10 }}>{t("hc.related")}</h3><div className="hc-grid">{rel.map((r) => <ArticleCard key={r.id} a={r} base={base} />)}</div></div>}
      <ContactCard />
    </div>
  );
  return mode === "app"
    ? <>{head}<PageHead title={a.title[lang]} />{content}</>
    : <section className="section"><div className="wrap-x">{head}<div className="sec-head" style={{ marginBottom: 24 }}><h2>{a.title[lang]}</h2></div>{content}</div></section>;
}
