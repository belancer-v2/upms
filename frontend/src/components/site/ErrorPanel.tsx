"use client";
import Link from "next/link";
import { Logo } from "@/components/Logo";
import { useT } from "@/lib/i18n";

/** Brand-style panel for the 404 and error pages. */
export function ErrorPanel({ kind, onRetry }: { kind: "404" | "error"; onRetry?: () => void }) {
  const { t } = useT();
  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
      <div className="card" style={{ maxWidth: 560, width: "100%", textAlign: "center", padding: "40px 28px" }}>
        <Link href="/" aria-label="FlatWise" style={{ display: "inline-block", marginBottom: 20 }}><Logo height={36} /></Link>
        <div style={{ fontSize: 76, fontWeight: 900, lineHeight: 1, background: "var(--spark)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }} aria-hidden>{kind === "404" ? "404" : "!"}</div>
        <h1 style={{ fontSize: 26, margin: "14px 0 8px" }}>{kind === "404" ? t("s2.err.404") : t("s2.err.title")}</h1>
        <p className="muted">{kind === "404" ? t("s2.err.404.sub") : t("s2.err.sub")}</p>
        <div className="row wrap" style={{ justifyContent: "center", gap: 10, marginTop: 20 }}>
          {onRetry && <button className="btn btn-primary" onClick={onRetry}>{t("s2.err.retry")}</button>}
          <Link className={`btn ${onRetry ? "btn-outline" : "btn-primary"}`} href="/">{t("s2.err.home")}</Link>
          <Link className="btn btn-ghost" href="/help">{t("s2.err.help")}</Link>
          <Link className="btn btn-ghost" href="/app">{t("s2.err.app")}</Link>
        </div>
      </div>
    </main>
  );
}
