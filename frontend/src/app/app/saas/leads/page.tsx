"use client";
import { useCallback, useEffect, useState } from "react";
import { Btn, Card, Chip, Modal, PageHead } from "@/components/ui";
import { api, fdate, ftime } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import { LeadMailTimeline } from "@/components/mailbits";

type Lead = { id: number; name: string; phone: string; email: string; building: string; flats: number; city: string; message: string; source: string; status: string; owner: string; owner_id: number | null; created_at: string; notes: { id: number; text: string; at: string; by: string }[] };
const COLS = ["new", "contacted", "demo", "trial", "won", "lost"];

export default function Leads() {
  const { t } = useT(); const { user } = useAuth();
  const [rows, setRows] = useState<Lead[]>([]); const [open, setOpen] = useState<Lead | null>(null); const [note, setNote] = useState("");
  const load = useCallback(() => api<Lead[]>("/saas/leads").then((r) => { setRows(r); setOpen((o) => (o ? r.find((x) => x.id === o.id) ?? null : null)); }), []);
  useEffect(() => { load(); }, [load]);
  const move = async (l: Lead, status: string) => { await api(`/saas/leads/${l.id}`, { method: "PATCH", body: { status, owner_id: l.owner_id ?? user?.id } }); load(); };
  const addNote = async () => { if (!open || !note.trim()) return; await api(`/saas/leads/${open.id}/notes`, { body: { text: note } }); setNote(""); load(); };
  return (
    <>
      <PageHead title={t("saas.leads.title")} sub={t("saas.leads.sub")} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(6, minmax(166px, 1fr))", gap: 14, overflowX: "auto", paddingBottom: 8 }}>
        {COLS.map((c) => {
          const list = rows.filter((r) => r.status === c);
          return (
            <div key={c} style={{ background: "var(--surface2)", border: "1.5px solid var(--line)", borderRadius: 18, padding: 12, minHeight: 300 }}>
              <div className="row between" style={{ marginBottom: 10 }}><b>{t(`lead.${c}`)}</b><Chip tone={c === "won" ? "ok" : c === "lost" ? "mute" : "info"}>{list.length}</Chip></div>
              <div className="col">
                {list.map((l) => (
                  <Card key={l.id} style={{ padding: 14, cursor: "pointer", boxShadow: "none" }}>
                    <div onClick={() => setOpen(l)}><b>{l.name}</b><div className="small muted">{l.building || "—"}{l.flats ? ` · ${t("saas.leads.flats", { n: l.flats })}` : ""}</div><div className="small muted">{l.city} · {l.owner || t("saas.leads.unassigned")}</div></div>
                    <select className="input" style={{ marginTop: 8, minHeight: 34, padding: "4px 8px", fontSize: 13 }} value={l.status} onChange={(e) => move(l, e.target.value)} aria-label={t("common.status")}>{COLS.map((s) => <option key={s} value={s}>{t(`lead.${s}`)}</option>)}</select>
                  </Card>))}
              </div>
            </div>
          );
        })}
      </div>
      {open && <Modal title={open.name} onClose={() => setOpen(null)}>
        <dl className="kv"><dt>{t("site.demo.building")}</dt><dd>{open.building || "—"} · {open.city}</dd><dt>{t("site.demo.flats")}</dt><dd>{open.flats || "—"}</dd><dt>{t("site.demo.phone")}</dt><dd>{open.phone}</dd><dt>{t("auth.email")}</dt><dd>{open.email || "—"}</dd><dt>{t("saas.leads.owner")}</dt><dd>{open.owner || t("saas.leads.unassigned")}</dd><dt>{t("common.date")}</dt><dd>{fdate(open.created_at)} · {open.source}</dd></dl>
        {open.message && <p style={{ marginTop: 14 }}>{open.message}</p>}
        <LeadMailTimeline leadId={open.id} />
        <h3 style={{ margin: "18px 0 8px" }}>{t("saas.leads.notes")}</h3>
        <ul className="list-dot">{open.notes.map((n) => <li key={n.id}><span>{n.text} <span className="muted small">· {n.by} · {ftime(n.at)}</span></span></li>)}</ul>
        <div className="row" style={{ marginTop: 12 }}><input className="input" placeholder={t("saas.leads.note")} value={note} onChange={(e) => setNote(e.target.value)} /><Btn onClick={addNote}>{t("saas.leads.add")}</Btn></div></Modal>}
    </>
  );
}
