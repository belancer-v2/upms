"use client";
import { useCallback, useEffect, useState } from "react";
import { Btn, Card, Chip, Empty, Field } from "@/components/ui";
import { api, ftime, money } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Cfg = { enabled: boolean; providers: string[]; fee_mode: string; fee_bps: number; has_credentials: boolean };
type Row = { id: number; unit: string; invoice: string; provider: string; amount: number; fee: number; charged: number; status: string; provider_ref: string; trx_id: string; created_at: string };
const PROVIDERS = ["bkash", "nagad", "card"];
const SIZE = 8;
const tone = (s: string) => (s === "paid" ? "ok" : s === "failed" ? "bad" : s === "expired" ? "mute" : "warn") as "ok" | "bad" | "mute" | "warn";

/** Collections > Charges: the building's online payment settings and the list of attempts. */
export function GatewayCard({ onSaved }: { onSaved?: (msg: string) => void }) {
  const { t } = useT();
  const [cfg, setCfg] = useState<Cfg | null>(null); const [pct, setPct] = useState("0"); const [cred, setCred] = useState(""); const [err, setErr] = useState("");
  const [rows, setRows] = useState<Row[]>([]); const [total, setTotal] = useState(0); const [page, setPage] = useState(1); const [q, setQ] = useState(""); const [st, setSt] = useState("");
  useEffect(() => { api<Cfg>("/gateway/config").then((c) => { setCfg(c); setPct(String(c.fee_bps / 100)); }).catch(() => setCfg(null)); }, []);
  const loadRows = useCallback(async () => { try { const r = await api<{ total: number; rows: Row[] }>(`/gateway/sessions?page=${page}&size=${SIZE}&q=${encodeURIComponent(q)}&status=${st}`); setRows(r.rows); setTotal(r.total); } catch { setRows([]); setTotal(0); } }, [page, q, st]);
  useEffect(() => { loadRows(); }, [loadRows]);
  if (!cfg) return null;
  const set = (k: Partial<Cfg>) => setCfg({ ...cfg, ...k });
  const toggle = (k: string) => set({ providers: cfg.providers.includes(k) ? cfg.providers.filter((x) => x !== k) : [...cfg.providers, k] });
  const save = async () => {
    setErr("");
    if (cfg.enabled && !cfg.providers.length) { setErr(t("gw.pick_one")); return; }
    try {
      const body: Record<string, unknown> = { enabled: cfg.enabled, providers: cfg.providers, fee_mode: cfg.fee_mode, fee_bps: Math.round((parseFloat(pct) || 0) * 100) };
      if (cred.trim()) body.credentials = { key: cred.trim() };
      const c = await api<Cfg>("/gateway/config", { method: "PUT", body }); setCfg(c); setCred(""); onSaved?.(t("gw.saved"));
    } catch (e: any) { setErr(e.message); }
  };
  const pages = Math.max(1, Math.ceil(total / SIZE));
  return (<Card>
    <div className="row between wrap"><div><h3 style={{ margin: 0 }}>{t("gw.title")}</h3><p className="hint" style={{ margin: "4px 0 0" }}>{t("gw.sub")}</p></div>
      <label className="row" style={{ cursor: "pointer" }}><input type="checkbox" role="switch" checked={cfg.enabled} onChange={(e) => set({ enabled: e.target.checked })} /> <b>{t("gw.enable")}</b></label></div>
    <p className="small muted" style={{ margin: "8px 0 12px" }}>{t("gw.sandbox_note")}</p>
    <div className="grid g2">
      <Field label={t("gw.providers")}><div className="row wrap">{PROVIDERS.map((k) => <label key={k} className="row" style={{ cursor: "pointer" }}><input type="checkbox" checked={cfg.providers.includes(k)} onChange={() => toggle(k)} /> {t(`gw.p.${k}`)}</label>)}</div></Field>
      <Field label={t("gw.fee_mode")}><select className="input" value={cfg.fee_mode} onChange={(e) => set({ fee_mode: e.target.value })}>{["building_absorbs", "payer_pays"].map((m) => <option key={m} value={m}>{t(`gw.fee.${m}`)}</option>)}</select></Field>
      <Field label={t("gw.fee_pct")} hint={t("gw.fee_hint")}><input className="input" inputMode="decimal" value={pct} onChange={(e) => setPct(e.target.value)} /></Field>
      <Field label={t("gw.cred")} hint={`${cfg.has_credentials ? t("gw.cred_set") : t("gw.cred_none")}. ${t("gw.cred_hint")}`}><input className="input" type="password" autoComplete="new-password" value={cred} onChange={(e) => setCred(e.target.value)} /></Field></div>
    {err && <p className="error" role="alert">{err}</p>}
    <div className="row" style={{ margin: "8px 0 20px" }}><Btn onClick={save}>{t("common.save")}</Btn></div>

    <h4 style={{ margin: "0 0 8px" }}>{t("gw.sessions")}</h4>
    <div className="toolbar row wrap"><input className="input" placeholder={t("common.search")} aria-label={t("common.search")} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
      <select className="input" style={{ width: "auto" }} value={st} onChange={(e) => { setSt(e.target.value); setPage(1); }} aria-label={t("gw.col.status")}><option value="">{t("gw.all")}</option>{["paid", "failed", "created", "expired"].map((s) => <option key={s} value={s}>{t(`gw.st.${s}`)}</option>)}</select></div>
    <div className="table-wrap"><table className="t"><thead><tr><th>{t("gw.col.when")}</th><th>{t("gw.col.flat")}</th><th>{t("gw.col.invoice")}</th><th>{t("gw.col.method")}</th><th className="num">{t("gw.col.amount")}</th><th className="num">{t("gw.col.fee")}</th><th>{t("gw.col.status")}</th><th>{t("gw.col.ref")}</th></tr></thead>
      <tbody>{rows.map((r) => <tr key={r.id}><td>{ftime(r.created_at)}</td><td>{r.unit}</td><td>{r.invoice}</td><td>{t(`gw.p.${r.provider}`)}</td><td className="num">{money(r.amount)}</td><td className="num">{money(r.fee)}</td><td><Chip tone={tone(r.status)}>{t(`gw.st.${r.status}`)}</Chip></td><td className="small">{r.trx_id || r.provider_ref}</td></tr>)}
        {!rows.length && <tr><td colSpan={8}><Empty /></td></tr>}</tbody></table></div>
    {total > SIZE && <div className="pager"><span className="small muted">{t("common.total")}: {total} · {t("common.page", { n: page, m: pages })}</span>
      <div className="row"><Btn variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>{t("common.prev")}</Btn><Btn variant="ghost" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>{t("common.next")}</Btn></div></div>}
  </Card>);
}
