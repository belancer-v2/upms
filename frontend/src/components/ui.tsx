"use client";
import { useEffect, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { useT } from "@/lib/i18n";

export function PageHead({ title, sub, actions, eyebrow }: { title: string; sub?: string; actions?: ReactNode; eyebrow?: string }) {
  return (
    <div className="page-head">
      <div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h1>{title}</h1>{sub && <p>{sub}</p>}</div>
      {actions && <div className="row wrap">{actions}</div>}
    </div>
  );
}
export const Card = ({ children, className = "", style }: { children: ReactNode; className?: string; style?: React.CSSProperties }) => <div className={`card ${className}`} style={style}>{children}</div>;
export const Stat = ({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) => (
  <div className="card stat"><span className="l">{label}</span><span className="v">{value}</span>{note && <span className="d">{note}</span>}</div>
);
export const Chip = ({ children, tone = "" }: { children: ReactNode; tone?: "ok" | "warn" | "bad" | "info" | "mute" | "" }) => <span className={`chip ${tone}`}>{children}</span>;
export function Btn({ variant = "primary", size, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "soft" | "ghost" | "outline" | "danger" | "light"; size?: "sm" | "lg" }) {
  return <button {...p} className={`btn btn-${variant} ${size ? "btn-" + size : ""} ${p.className ?? ""}`} />;
}
export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <div className="field"><label>{label}</label>{children}{hint && <span className="hint">{hint}</span>}</div>;
}
export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const { t } = useT();
  useEffect(() => { const k = (e: KeyboardEvent) => e.key === "Escape" && onClose(); window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, [onClose]);
  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-label={title}>
        <div className="row between" style={{ marginBottom: 14 }}><h2>{title}</h2><button className="icon-btn" aria-label={t("common.close")} onClick={onClose}>✕</button></div>
        {children}
      </div>
    </div>
  );
}
export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { id: T; label: string }[] }) {
  return <div className="tabs" role="tablist">{items.map((i) => <button key={i.id} role="tab" aria-selected={value === i.id} className={`tab ${value === i.id ? "on" : ""}`} onClick={() => onChange(i.id)}>{i.label}</button>)}</div>;
}
export const Empty = ({ children }: { children?: ReactNode }) => { const { t } = useT(); return <div className="empty">{children ?? t("common.none")}</div>; };
export const Bar = ({ pct, spark }: { pct: number; spark?: boolean }) => <div className={`bar ${spark ? "sparked" : ""}`}><i style={{ width: `${Math.max(2, Math.min(100, pct))}%` }} /></div>;

export type Col<R> = { key: string; head: string; render?: (r: R) => ReactNode; num?: boolean };
/** Every long list in FlatWise is searchable and has a numbered pager. Page size is fixed here; admins can change it later (setting). */
export function DataTable<R extends { id: number | string }>({ rows, cols, pageSize = 10, search, onRow }: { rows: R[]; cols: Col<R>[]; pageSize?: number; search?: (r: R) => string; onRow?: (r: R) => void }) {
  const { t } = useT();
  const [q, setQ] = useState(""); const [page, setPage] = useState(1);
  const filtered = q && search ? rows.filter((r) => search(r).toLowerCase().includes(q.toLowerCase())) : rows;
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  useEffect(() => { if (page > pages) setPage(1); }, [pages, page]);
  const view = filtered.slice((page - 1) * pageSize, page * pageSize);
  return (
    <div>
      {search && <div className="toolbar"><input className="input" placeholder={t("common.search")} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} aria-label={t("common.search")} /></div>}
      <div className="table-wrap">
        <table className="t">
          <thead><tr>{cols.map((c) => <th key={c.key} className={c.num ? "num" : ""}>{c.head}</th>)}</tr></thead>
          <tbody>
            {view.map((r) => <tr key={r.id} onClick={() => onRow?.(r)} style={onRow ? { cursor: "pointer" } : undefined}>{cols.map((c) => <td key={c.key} className={c.num ? "num" : ""}>{c.render ? c.render(r) : String((r as any)[c.key] ?? "")}</td>)}</tr>)}
            {!view.length && <tr><td colSpan={cols.length}><Empty /></td></tr>}
          </tbody>
        </table>
      </div>
      {filtered.length > pageSize && (
        <div className="pager"><span className="small muted">{t("common.total")}: {filtered.length} · {t("common.page", { n: page, m: pages })}</span>
          <div className="row"><Btn variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>{t("common.prev")}</Btn>
            <Btn variant="ghost" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>{t("common.next")}</Btn></div></div>
      )}
    </div>
  );
}

let toastTimer: ReturnType<typeof setTimeout>;
export function useToast() {
  const [msg, setMsg] = useState("");
  const show = (m: string) => { setMsg(m); clearTimeout(toastTimer); toastTimer = setTimeout(() => setMsg(""), 2600); };
  return { show, node: msg ? <div className="toast" role="status">{msg}</div> : null };
}
