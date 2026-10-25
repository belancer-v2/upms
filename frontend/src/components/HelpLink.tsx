"use client";
import Link from "next/link";
import "./help/help.css";
import type { HelpId } from "@/lib/help/types";
import { useT } from "@/lib/i18n";

/** The small "?" next to a page title. It opens the help article for that screen. */
export function HelpLink({ id }: { id: HelpId }) {
  const { t } = useT();
  return <Link href={`/app/help/${id}`} className="help-q" aria-label={t("hc.helpbtn")} title={t("hc.helpbtn")}>?</Link>;
}
