"use client";
import { Chip } from "@/components/ui";
import { useT } from "@/lib/i18n";

export function BillChip({ s }: { s: string }) {
  const { t } = useT();
  const tone = s === "paid" || s === "verified" ? "ok" : s === "overdue" || s === "rejected" ? "bad" : s === "void" ? "mute" : s === "open" ? "mute" : "warn";
  return <Chip tone={tone}>{t(`bill.st.${s}`)}</Chip>;
}
export const stColor = (s?: string) =>
  s === "paid" ? { bg: "var(--ok-bg)", fg: "var(--ok)" } : s === "overdue" ? { bg: "var(--bad-bg)", fg: "var(--bad)" } : s === "partial" ? { bg: "var(--warn-bg)", fg: "var(--warn)" }
    : s === "open" ? { bg: "var(--blush)", fg: "var(--blush-text)" } : { bg: "var(--surface2)", fg: "var(--muted)", ring: "var(--line)" };
export type Inv = { id: number; number: string; unit_id: number; unit: string; floor: number; period: string; issue_date: string; due_date: string; total: number; paid: number; balance: number; status: string; lines?: { description: string; description_bn: string; amount: number }[]; payments?: Pay[] };
export type Pay = { id: number; invoice_id: number; unit_id: number; amount: number; method: string; trx_id: string; paid_on: string; status: string; receipt_no: string; note: string; unit?: string; period?: string };
