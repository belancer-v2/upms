"use client";
import { useEffect, useState } from "react";
import { Card, Chip } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type D = { post: string; post_bn: string; shift: string; shift_bn: string; start: string; end: string; name: string; name_bn: string; agency: string; agency_bn: string };

/** Read-only "who is on duty now" for residents and staff. Names, posts and the agency name only: no phone numbers. */
export function DutyStrip({ compact = false }: { compact?: boolean }) {
  const { t, pick } = useT(); const { prop, feature } = useAuth(); const [rows, setRows] = useState<D[] | null>(null);
  useEffect(() => { if (!prop || !feature("staff")) { setRows(null); return; } api<{ items: D[] }>("/agency/duty").then((r) => setRows(r.items)).catch(() => setRows(null)); }, [prop?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  if (rows === null) return null;
  return (
    <Card style={{ gridColumn: "1 / -1" }}>
      <h3 style={{ margin: 0 }}>{compact ? t("ag.duty.card") : t("ag.duty.title")}</h3>
      {!compact && <p className="small muted" style={{ margin: "4px 0 10px" }}>{t("ag.duty.sub")}</p>}
      {rows.length === 0 ? <p className="muted small" style={{ marginTop: 10 }}>{t("ag.duty.none")}</p> : (
        <div className="row wrap" style={{ gap: 10, marginTop: 10 }}>
          {rows.map((r, i) => (
            <div key={i} style={{ border: "1.5px solid var(--line)", borderRadius: 12, padding: "8px 12px", background: "var(--surface2)", minWidth: 190 }}>
              <b>{pick(r.name, r.name_bn || r.name)}</b>
              <div className="small muted">{pick(r.post, r.post_bn || r.post)} · {r.start}–{r.end}</div>
              {r.agency ? <Chip tone="info">{pick(r.agency, r.agency_bn || r.agency)}</Chip> : <Chip tone="mute">{t("ag.direct")}</Chip>}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
