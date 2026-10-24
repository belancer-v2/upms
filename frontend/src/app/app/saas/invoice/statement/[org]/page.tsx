"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Btn } from "@/components/ui";
import { SHEET_CSS, SheetHead, makeL } from "@/components/invoicedoc";
import { api, fdate, money } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function Statement() {
  const { t, lang } = useT();
  const { org } = useParams<{ org: string }>();
  const [d, setD] = useState<any>(null); const [err, setErr] = useState("");
  useEffect(() => { api(`/saas/invoices-doc/statement/${org}`).then(setD).catch((e) => setErr(e.message)); }, [org]);
  if (err) return <p className="muted">{err}</p>;
  if (!d) return <p className="muted">{t("common.loading")}</p>;
  const L = makeL(lang), bn = lang === "bn";
  return (
    <>
      <style>{SHEET_CSS}</style>
      <div className="no-print row wrap" style={{ maxWidth: "210mm", margin: "0 auto 14px", gap: 8 }}>
        <Link href="/app/saas/invoices" className="btn btn-ghost btn-sm">{t("idoc.act.back")}</Link><Btn onClick={() => window.print()}>{t("idoc.act.print")}</Btn>
      </div>
      <div className="sheet">
        <SheetHead c={d.company} lang={lang} title={L("idoc.statement")}><div className="soft">{L("idoc.upto")}</div><div className="soft">{fdate(new Date().toISOString())}</div></SheetHead>
        <div className="box" style={{ marginBottom: 12 }}><div className="cap">{L("idoc.billto")}</div><b>{bn && d.customer.name_bn ? d.customer.name_bn : d.customer.name}</b><div className="soft">{[d.customer.address, d.customer.city].filter(Boolean).join(", ")}</div></div>
        <table><thead><tr><th>{L("idoc.d.date")}</th><th>{L("idoc.d.type")}</th><th>{L("idoc.d.ref")}</th><th>{L("idoc.d.desc")}</th><th className="num">{L("idoc.d.debit")}</th><th className="num">{L("idoc.d.credit")}</th><th className="num">{L("idoc.d.balance")}</th></tr></thead>
          <tbody>{d.rows.map((r: any, n: number) => <tr key={n}><td className="num" style={{ textAlign: "left" }}>{fdate(r.date)}</td><td>{L(`idoc.t.${r.type}`)}</td><td><Link href={`/app/saas/invoice/${r.invoice_id}`}>{r.ref}</Link></td><td>{r.description}</td>
            <td className="num">{r.debit ? money(r.debit) : ""}</td><td className="num">{r.credit ? money(r.credit) : ""}</td><td className="num">{money(r.balance)}</td></tr>)}</tbody></table>
        <div className="tot"><div className="grand"><span>{L("idoc.closing", { d: fdate(new Date().toISOString()) })}</span><span>{money(d.balance)}</span></div></div>
        <div className="foot">{bn && d.company.footer_text_bn ? d.company.footer_text_bn : d.company.footer_text}</div>
      </div>
    </>
  );
}
