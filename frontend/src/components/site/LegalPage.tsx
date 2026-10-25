"use client";
import Link from "next/link";
import { Ph } from "@/components/Placeholder";
import { COMPANY, LEGAL_REVIEWED, LEGAL_UPDATED } from "@/lib/company";
import { fill, LEGAL, type LegalId } from "@/lib/legal";
import { useT } from "@/lib/i18n";

const OTHERS: [LegalId, string][] = [["terms", "s2.nav.terms"], ["privacy", "s2.nav.privacy"], ["refund", "s2.nav.refund"]];

export function LegalPage({ id }: { id: LegalId }) {
  const { t, lang } = useT();
  const doc = LEGAL[id];
  return (
    <section className="section"><div className="wrap-x" style={{ maxWidth: 860 }}>
      <div className="sec-head" style={{ marginBottom: 24 }}><div className="eyebrow">{t("s2.nav.legal")}</div><h2>{doc.title[lang]}</h2><p className="small" style={{ fontSize: 14 }}>{t("s2.legal.updated", { d: LEGAL_UPDATED })}</p></div>
      {!LEGAL_REVIEWED && <div className="card" role="note" style={{ marginBottom: 22, borderColor: "var(--warn)", background: "var(--warn-bg)", color: "var(--warn)", fontWeight: 700 }}>{t("s2.legal.draft")}</div>}
      <p style={{ fontSize: 18 }}><Ph text={fill(doc.intro[lang], lang, COMPANY)} /></p>
      {doc.sections.map((s, i) => (
        <section key={i} style={{ marginTop: 28 }}><h3 style={{ marginBottom: 10 }}>{s.h[lang]}</h3>{s.p.map((p, j) => <p key={j}><Ph text={fill(p[lang], lang, COMPANY)} /></p>)}</section>
      ))}
      <hr style={{ border: 0, borderTop: "1.5px solid var(--line)", margin: "36px 0 16px" }} />
      <p className="small muted">{t("s2.legal.others")}: {OTHERS.filter(([k]) => k !== id).map(([k, key], i) => <span key={k}>{i > 0 && " · "}<Link href={`/${k}`}>{t(key)}</Link></span>)}</p>
    </div></section>
  );
}
