"use client";
/** Printable A4 sheets for FlatWise tax invoices, credit notes and statements. The sheet is written in the invoice's own language, whatever the screen language is. */
import type { ReactNode } from "react";
import { fdate, money } from "@/lib/api";
import { dict } from "@/lib/dict";

export type DocLang = "en" | "bn";
export const makeL = (lang: DocLang) => (key: string, vars?: Record<string, string | number>) => {
  let s = dict[lang][key] ?? dict.en[key] ?? key;
  if (vars) for (const k of Object.keys(vars)) s = s.replaceAll(`{${k}}`, String(vars[k]));
  return s;
};

export const SHEET_CSS = `
.sheet{--paper:#ffffff;--ink:#1b1b1f;--soft:#5d5d66;--rule:#d9d9de;background:var(--paper);color:var(--ink);width:100%;max-width:210mm;margin:0 auto;padding:14mm 14mm 12mm;border:1px solid var(--rule);border-radius:6px;box-shadow:0 8px 28px rgba(0,0,0,.12);font-size:13.5px;line-height:1.45;position:relative;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.sheet h1{font-size:24px;margin:0;letter-spacing:-.01em;color:var(--ink)} .sheet h2,.sheet h3{color:var(--ink);margin:0}
.sheet .soft{color:var(--soft)} .sheet .cap{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--soft);font-weight:800;margin-bottom:3px}
html[lang="bn"] .sheet .cap{letter-spacing:0;text-transform:none;font-size:12px}
.sheet .hd{display:flex;justify-content:space-between;gap:16px;border-bottom:2px solid var(--ink);padding-bottom:12px;margin-bottom:14px}
.sheet .logo{max-height:54px;max-width:180px;object-fit:contain;display:block;margin-bottom:6px}
.sheet table{width:100%;border-collapse:collapse} .sheet th{text-align:left;font-size:11.5px;color:var(--soft);padding:7px 8px;border-bottom:1.5px solid var(--ink)} .sheet td{padding:8px;border-bottom:1px solid var(--rule);vertical-align:top}
.sheet .num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.sheet .tot{margin-left:auto;width:min(100%,300px);margin-top:10px} .sheet .tot div{display:flex;justify-content:space-between;padding:4px 8px} .sheet .tot .grand{border-top:2px solid var(--ink);font-weight:900;font-size:15px;margin-top:4px;padding-top:8px}
.sheet .stamp{position:absolute;right:18mm;top:44mm;transform:rotate(-10deg);border:3px solid;border-radius:8px;padding:2px 16px;font-size:26px;font-weight:900;letter-spacing:.08em;opacity:.8;pointer-events:none}
.sheet .stamp.paid{color:#007C75} .sheet .stamp.due{color:#8A5C00} .sheet .stamp.void{color:#971B1E} .sheet .stamp.overdue{color:#971B1E}
.sheet .box{border:1px solid var(--rule);border-radius:8px;padding:10px 12px} .sheet .cols{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:12px 0}
.sheet .foot{border-top:1px solid var(--rule);margin-top:16px;padding-top:8px;font-size:12px;color:var(--soft)} .sheet pre{white-space:pre-wrap;font:inherit;margin:0}
@media (max-width:640px){.sheet{padding:16px}.sheet .hd,.sheet .cols{display:block}.sheet .stamp{top:96px;right:16px}}
@media print{@page{size:A4;margin:10mm}.sheet{border:none;box-shadow:none;border-radius:0;max-width:none;padding:0}.sheet .stamp{top:36mm}}
`;

type Company = { legal_name: string; legal_name_bn: string; address: string; address_bn: string; phone: string; email: string; bin_no: string; tin: string; logo_url: string; footer_text: string; footer_text_bn: string; bank_details: string; bkash_merchant: string; nagad_merchant: string };

export function SheetHead({ c, lang, title, children }: { c: Company; lang: DocLang; title: string; children?: ReactNode }) {
  const L = makeL(lang), bn = lang === "bn";
  return (
    <div className="hd">
      <div>{c.logo_url && /* eslint-disable-next-line @next/next/no-img-element */ <img className="logo" src={c.logo_url} alt="" />}
        <h2>{bn && c.legal_name_bn ? c.legal_name_bn : c.legal_name}</h2>
        <div className="soft">{bn && c.address_bn ? c.address_bn : c.address}</div>
        <div className="soft">{[c.phone, c.email].filter(Boolean).join(" · ")}</div>
        <div className="soft">{c.bin_no && `${L("idoc.bin")}: ${c.bin_no}`}{c.bin_no && c.tin ? " · " : ""}{c.tin && `${L("idoc.tin")}: ${c.tin}`}</div></div>
      <div style={{ textAlign: "right" }}><h1>{title}</h1>{children}</div>
    </div>
  );
}

export function Stamp({ kind, lang }: { kind: "paid" | "due" | "void" | "overdue"; lang: DocLang }) {
  const L = makeL(lang);
  return <div className={`stamp ${kind}`}>{L(kind === "paid" ? "idoc.paid" : kind === "void" ? "idoc.void" : kind === "overdue" ? "idoc.overdue" : "idoc.due_stamp")}</div>;
}

export function InvoiceSheet({ d }: { d: any }) {
  const lang: DocLang = d.lang === "bn" ? "bn" : "en", L = makeL(lang), bn = lang === "bn";
  const c: Company = d.company;
  const stamp = d.stamp === "due" && d.overdue ? "overdue" : d.stamp;
  return (
    <div className="sheet" lang={lang}>
      <Stamp kind={stamp} lang={lang} />
      <SheetHead c={c} lang={lang} title={L("idoc.invoice")}>
        <div><b>{L("idoc.no")}:</b> {d.doc_no ?? "-"}</div>
        <div className="soft">{L("idoc.quote")}: {d.quote_ref}</div>
        <div className="soft">{L("idoc.date")}: {d.issued_at ? fdate(d.issued_at) : "-"}</div>
        <div className="soft">{L("idoc.due")}: {fdate(d.due_at)}</div>
      </SheetHead>
      <div className="cols">
        <div className="box"><div className="cap">{L("idoc.billto")}</div><b>{bn && d.customer.name_bn ? d.customer.name_bn : d.customer.name}</b>
          <div className="soft">{[d.customer.address, d.customer.city].filter(Boolean).join(", ")}</div>{d.customer.contacts[0] && <div className="soft">{d.customer.contacts[0].name} · {d.customer.contacts[0].email}</div>}</div>
        <div className="box"><div className="cap">{L("idoc.period")}</div><b>{d.period || "-"}</b>
          {d.paid_at && <div className="soft">{L("idoc.paid_on", { d: fdate(d.paid_at), m: d.method, t: d.trx_id })}</div>}
          {d.credited > 0 && <div className="soft">{L("idoc.credits")}: {money(d.credited)}</div>}
          {d.stamp !== "void" && d.balance > 0 && <div><b>{L("idoc.balance")}: {money(d.balance)}</b></div>}</div>
      </div>
      <table><thead><tr><th>{L("idoc.item")}</th><th className="num">{L("idoc.qty")}</th><th className="num">{L("idoc.amount")}</th></tr></thead>
        <tbody>{d.items.map((i: any, n: number) => <tr key={n}><td>{bn ? i.desc_bn : i.desc}</td><td className="num">{i.qty}</td><td className="num">{money(i.net)}</td></tr>)}</tbody></table>
      <div className="tot"><div><span>{L("idoc.subtotal")}</span><span>{money(d.subtotal)}</span></div><div><span>{L("idoc.vat", { p: d.vat_pct })}</span><span>{money(d.vat)}</span></div><div className="grand"><span>{L("idoc.total")}</span><span>{money(d.total)}</span></div></div>
      <div className="box" style={{ marginTop: 12 }}><div className="cap">{L("idoc.words")}</div><div><b>{bn ? d.words_bn : d.words_en}</b></div><div className="soft" lang={bn ? "en" : "bn"}>{bn ? d.words_en : d.words_bn}</div></div>
      {d.credit_notes.length > 0 && <div style={{ marginTop: 12 }}><div className="cap">{L("idoc.credits")}</div>{d.credit_notes.map((cn: any) => <div key={cn.id} className="row between"><span>{cn.doc_no} · {fdate(cn.issued_at)} · {cn.reason}</span><b>-{money(cn.amount)}</b></div>)}</div>}
      {d.stamp === "due" && <div className="cols">
        <div className="box"><div className="cap">{L("idoc.pay")}</div>
          {c.bkash_merchant && <div>{L("idoc.bkash")}: <b>{c.bkash_merchant}</b></div>}{c.nagad_merchant && <div>{L("idoc.nagad")}: <b>{c.nagad_merchant}</b></div>}
          <div className="soft">{L("idoc.payref", { ref: d.payment.reference })}</div></div>
        <div className="box"><div className="cap">{L("idoc.bank")}</div><pre>{c.bank_details || "-"}</pre></div></div>}
      <div className="foot">{bn && c.footer_text_bn ? c.footer_text_bn : c.footer_text}</div>
    </div>
  );
}

export function CreditSheet({ d, inv }: { d: any; inv: any }) {
  const lang: DocLang = d.lang === "bn" ? "bn" : "en", L = makeL(lang), bn = lang === "bn";
  const c: Company = d.company;
  return (
    <div className="sheet" lang={lang}>
      <SheetHead c={c} lang={lang} title={L("idoc.credit")}>
        <div><b>{L("idoc.cn_no")}:</b> {d.doc_no}</div><div className="soft">{L("idoc.date")}: {fdate(d.issued_at)}</div><div className="soft">{L("idoc.against")}: {d.invoice_no}</div>
      </SheetHead>
      <div className="cols"><div className="box"><div className="cap">{L("idoc.billto")}</div><b>{bn && d.customer.name_bn ? d.customer.name_bn : d.customer.name}</b><div className="soft">{[d.customer.address, d.customer.city].filter(Boolean).join(", ")}</div></div>
        <div className="box"><div className="cap">{L("idoc.reason")}</div><b>{d.reason}</b><div className="soft">{L("idoc.cn_note", { n: d.invoice_no })}</div></div></div>
      <table><thead><tr><th>{L("idoc.item")}</th><th className="num">{L("idoc.amount")}</th></tr></thead><tbody><tr><td>{L("idoc.credit")} · {d.invoice_no}{inv ? ` · ${bn ? inv.items[0]?.desc_bn : inv.items[0]?.desc}` : ""}</td><td className="num">-{money(d.net)}</td></tr></tbody></table>
      <div className="tot"><div><span>{L("idoc.subtotal")}</span><span>-{money(d.net)}</span></div><div><span>{L("idoc.vat", { p: d.vat_pct })}</span><span>-{money(d.vat)}</span></div><div className="grand"><span>{L("idoc.total")}</span><span>-{money(d.amount)}</span></div></div>
      <div className="box" style={{ marginTop: 12 }}><div className="cap">{L("idoc.words")}</div><div><b>{bn ? d.words_bn : d.words_en}</b></div></div>
      <div className="foot">{bn && c.footer_text_bn ? c.footer_text_bn : c.footer_text}</div>
    </div>
  );
}
