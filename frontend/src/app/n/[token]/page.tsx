"use client";
import { use, useEffect, useState } from "react";
import { Logo } from "@/components/Logo";
import { Toggles } from "@/components/Toggles";
import { api, fdate } from "@/lib/api";
import { useT } from "@/lib/i18n";

type P = { building: string; building_bn: string; title: string; title_bn: string; body: string; body_bn: string; priority: string; at: string; for: string };
export default function Link({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params); const { t, pick } = useT(); const [p, setP] = useState<P | null>(null); const [err, setErr] = useState(false);
  useEffect(() => { api<P>(`/notices/link/${token}`).then(setP).catch(() => setErr(true)); }, [token]);
  return (<div style={{ maxWidth: 620, margin: "0 auto", padding: "20px 16px 60px" }}>
    <div className="row between" style={{ marginBottom: 24 }}><Logo /><Toggles /></div>
    {err && <div className="card"><p>{t("nt.gone")}</p></div>}
    {p && <div className="card"><div className="eyebrow">{t("nt.link_title")} · {pick(p.building, p.building_bn || p.building)}</div><h1 style={{ margin: "8px 0 4px", fontSize: 26 }}>{pick(p.title, p.title_bn || p.title)}</h1><span className="small muted">{fdate(p.at)}</span>
      <p style={{ whiteSpace: "pre-wrap", marginTop: 16, fontSize: 17, lineHeight: 1.6 }}>{pick(p.body, p.body_bn || p.body)}</p><p className="hint" style={{ marginTop: 20 }}>{t("nt.link_foot")}</p></div>}
  </div>);
}
