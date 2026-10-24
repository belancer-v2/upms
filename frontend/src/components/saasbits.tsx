"use client";
import { Chip } from "@/components/ui";
import { useT } from "@/lib/i18n";

export function SubChip({ s }: { s: string }) {
  const { t } = useT();
  const tone = s === "active" ? "ok" : s === "trial" ? "info" : s === "past_due" ? "warn" : s === "suspended" ? "bad" : "mute";
  return <Chip tone={tone}>{t(`sub.${s}`)}</Chip>;
}
export function InvChip({ s }: { s: string }) {
  const { t } = useT();
  return <Chip tone={s === "paid" ? "ok" : s === "overdue" ? "bad" : s === "void" ? "mute" : "warn"}>{t(`inv.${s}`)}</Chip>;
}
export const daysLeft = (iso: string | null) => (iso ? Math.ceil((new Date(iso).getTime() - Date.now()) / 86400000) : 0);
