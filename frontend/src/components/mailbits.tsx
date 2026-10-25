"use client";
import { useCallback, useEffect, useState } from "react";
import { Chip } from "@/components/ui";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

export type Block = { type: "heading" | "paragraph" | "button" | "image" | "divider" | "footer"; text?: string; label?: string; url?: string; alt?: string };

export function StatusChip({ s }: { s: string }) {
  const { t } = useT();
  const tone = s === "sent" || s === "delivered" ? "ok" : s === "scheduled" || s === "sending" || s === "queued" ? "info" : s === "bounced" || s === "failed" ? "bad" : s === "suppressed" || s === "skipped" ? "warn" : "mute";
  return <Chip tone={tone}>{t(`mail.st.${s}`)}</Chip>;
}

/** A rendered email in a sandboxed iframe. No scripts run, so the preview cannot touch the app. */
export function EmailFrame({ html, mobile, height = 560 }: { html: string; mobile?: boolean; height?: number }) {
  const { t } = useT();
  return (
    <div style={{ display: "flex", justifyContent: "center", background: "var(--surface2)", border: "1.5px solid var(--line)", borderRadius: 14, padding: 10, overflow: "auto" }}>
      <iframe title={t("a11y.email_preview")} sandbox="" srcDoc={html} style={{ width: mobile ? 375 : "100%", maxWidth: "100%", height, border: 0, background: "transparent", borderRadius: 8 }} />
    </div>
  );
}

/** Server paged list with search. Every long list has search and a numbered pager. */
export function usePaged<T>(path: string, extra: Record<string, string | number> = {}, size = 10) {
  const [q, setQ] = useState(""); const [page, setPage] = useState(1);
  const [data, setData] = useState<{ items: T[]; total: number }>({ items: [], total: 0 });
  const key = JSON.stringify(extra);
  const load = useCallback(() => {
    const qs = new URLSearchParams({ page: String(page), size: String(size), q, ...Object.fromEntries(Object.entries(JSON.parse(key)).map(([k, v]) => [k, String(v)])) });
    return api<{ items: T[]; total: number }>(`${path}?${qs}`).then(setData).catch(() => {});
  }, [path, page, size, q, key]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { setPage(1); }, [q, key]);
  return { ...data, page, size, setPage, q, setQ, reload: load };
}

export const pct = (n: number) => `${n.toFixed(1)}%`;

type TlEvent = { outbox_id: number; name: string; name_bn: string; event: string; at: string };
/** "Email: Welcome sent / opened" entries and the consent source, shown on the lead page. */
export function LeadMailTimeline({ leadId }: { leadId: number }) {
  const { t, pick } = useT();
  const [d, setD] = useState<{ consent: { source: string } | null; suppressed: string; events: TlEvent[] } | null>(null);
  useEffect(() => { api<any>(`/saas/mail/leads/${leadId}/timeline`).then(setD).catch(() => setD(null)); }, [leadId]);
  if (!d) return null;
  return (
    <>
      <h3 style={{ margin: "18px 0 8px" }}>{t("mail.lead.title")}</h3>
      <p className="small muted" style={{ margin: "0 0 6px" }}>{t("mail.lead.consent")}: {d.consent ? d.consent.source : "—"}{d.suppressed && <> · <Chip tone="warn">{t("mail.lead.suppressed")}</Chip></>}</p>
      <ul className="list-dot">{d.events.slice(0, 8).map((e, i) => <li key={i}><span>{t("mail.lead.ev", { n: pick(e.name, e.name_bn), e: t(`mail.ev.${e.event}`) })} <span className="muted small">· {new Date(e.at).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</span></span></li>)}
        {!d.events.length && <li><span className="muted small">{t("mail.lead.none")}</span></li>}</ul>
    </>
  );
}
