"use client";
import { Children, cloneElement, isValidElement, useEffect, useId, useRef, useState, type ButtonHTMLAttributes, type ReactElement, type ReactNode } from "react";
import { useT } from "@/lib/i18n";
import { HelpLink } from "./HelpLink";
import type { HelpId } from "@/lib/help/types";

export function PageHead({ title, sub, actions, eyebrow, helpKey }: { title: string; sub?: string; actions?: ReactNode; eyebrow?: string; helpKey?: HelpId }) {
  return (
    <div className="page-head">
      <div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h1>{title}{helpKey && <HelpLink id={helpKey} />}</h1>{sub && <p>{sub}</p>}</div>
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
/** A labelled form row. A single input, select or textarea is tied to its label (for/id) and its hint; any other content is announced as a group named by the label. */
export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  const id = useId(); const hintId = hint ? `${id}-hint` : undefined;
  const kids = Children.toArray(children); const only = kids.length === 1 ? kids[0] : null;   // null and false children do not count
  const control = isValidElement(only) && typeof only.type === "string" && ["input", "select", "textarea"].includes(only.type) ? (only as ReactElement<{ id?: string; "aria-describedby"?: string }>) : null;
  const forId = control ? control.props.id ?? id : undefined;
  return (
    <div className="field" {...(control ? {} : { role: "group", "aria-labelledby": `${id}-label` })}>
      <label id={`${id}-label`} htmlFor={forId}>{label}</label>
      {control ? cloneElement(control, { id: forId, "aria-describedby": control.props["aria-describedby"] ?? hintId }) : children}
      {hint && <span className="hint" id={hintId}>{hint}</span>}
    </div>
  );
}
const modalStack: symbol[] = [];
const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
/** Dialog: named by its title, focus moves in on open, Tab stays inside, Escape closes only the top dialog, focus returns to the button that opened it. */
export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const { t } = useT();
  const box = useRef<HTMLDivElement>(null); const titleId = useId(); const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const me = Symbol("modal"); modalStack.push(me);
    const opener = document.activeElement as HTMLElement | null;
    const list = () => Array.from(box.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []).filter((el) => el.getClientRects().length > 0);
    const first = list().find((el) => !el.classList.contains("icon-btn")) ?? list()[0] ?? box.current;
    first?.focus();
    const key = (e: KeyboardEvent) => {
      if (modalStack[modalStack.length - 1] !== me) return;
      if (e.key === "Escape") { e.stopPropagation(); closeRef.current(); return; }
      if (e.key !== "Tab") return;
      const f = list(); if (!f.length) { e.preventDefault(); return; }
      const a = document.activeElement;
      if (e.shiftKey && (a === f[0] || !box.current?.contains(a))) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && (a === f[f.length - 1] || !box.current?.contains(a))) { e.preventDefault(); f[0].focus(); }
    };
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("keydown", key); modalStack.splice(modalStack.indexOf(me), 1); if (opener && document.contains(opener)) opener.focus(); };
  }, []);
  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby={titleId} ref={box} tabIndex={-1}>
        <div className="row between" style={{ marginBottom: 14 }}><h2 id={titleId}>{title}</h2><button className="icon-btn" aria-label={t("common.close")} onClick={onClose}>✕</button></div>
        {children}
      </div>
    </div>
  );
}
export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { id: T; label: string }[] }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  /** Arrow keys, Home and End move between tabs (one tab stop for the whole list). */
  const onKey = (e: React.KeyboardEvent, i: number) => {
    const n = items.length;
    const j = e.key === "ArrowRight" || e.key === "ArrowDown" ? (i + 1) % n : e.key === "ArrowLeft" || e.key === "ArrowUp" ? (i - 1 + n) % n : e.key === "Home" ? 0 : e.key === "End" ? n - 1 : -1;
    if (j < 0) return;
    e.preventDefault(); onChange(items[j].id); refs.current[j]?.focus();
  };
  return <div className="tabs" role="tablist">{items.map((i, n) => <button key={i.id} ref={(el) => { refs.current[n] = el; }} role="tab" aria-selected={value === i.id} tabIndex={value === i.id ? 0 : -1} className={`tab ${value === i.id ? "on" : ""}`} onKeyDown={(e) => onKey(e, n)} onClick={() => onChange(i.id)}>{i.label}</button>)}</div>;
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
            {view.map((r) => <tr key={r.id} onClick={() => onRow?.(r)} onKeyDown={onRow ? (e) => { if (e.key === "Enter" && e.target === e.currentTarget) onRow(r); } : undefined} tabIndex={onRow ? 0 : undefined} style={onRow ? { cursor: "pointer" } : undefined}>{cols.map((c) => <td key={c.key} className={c.num ? "num" : ""}>{c.render ? c.render(r) : String((r as any)[c.key] ?? "")}</td>)}</tr>)}
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
