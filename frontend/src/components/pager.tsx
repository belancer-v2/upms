"use client";
import { Btn } from "@/components/ui";
import { useT } from "@/lib/i18n";

/** Numbered pager for lists the server pages (it returns total). */
export function Pager({ page, size, total, onPage }: { page: number; size: number; total: number; onPage: (p: number) => void }) {
  const { t } = useT();
  const pages = Math.max(1, Math.ceil(total / size));
  if (total <= size) return null;
  return (
    <div className="pager"><span className="small muted">{t("common.total")}: {total} · {t("common.page", { n: page, m: pages })}</span>
      <div className="row"><Btn variant="ghost" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>{t("common.prev")}</Btn>
        <Btn variant="ghost" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>{t("common.next")}</Btn></div></div>
  );
}
