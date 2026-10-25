/** Turns an audit action such as "parking.vehicle.add" into words in the interface language (area: what happened). Unknown words stay as written. */
export function actionLabel(t: (k: string) => string, action: string): string {
  const has = (k: string) => t(k) !== k;
  const parts = action.split(".");
  const dom = has(`act.d.${parts[0]}`) ? t(`act.d.${parts[0]}`) : parts[0].replace(/_/g, " ");
  if (parts.length === 1) return dom;
  const rest = parts.slice(1).map((p) => {
    if (has(`act.w.${p}`)) return t(`act.w.${p}`);
    return p.replace(/[{}]/g, "").split("_").map((w) => (has(`act.w.${w}`) ? t(`act.w.${w}`) : w)).join(" ");
  }).join(" ");
  return rest.toLowerCase() === dom.toLowerCase() ? dom : `${dom}: ${rest}`;
}

/** The thing an action was done to ("parking_slot" becomes words in the interface language). */
export function entityLabel(t: (k: string) => string, entity: string): string {
  const has = (k: string) => t(k) !== k;
  return entity.split("_").map((w) => (has(`act.w.${w}`) ? t(`act.w.${w}`) : has(`act.d.${w}`) ? t(`act.d.${w}`) : w)).join(" ");
}

/** A stored key such as a plan ("pro") or a lead source ("referral") shown as a word in the interface language. Unknown keys are capitalised. */
export function keyLabel(t: (k: string) => string, s: string): string {
  for (const ns of ["plan.name", "lead.src"]) { const k = `${ns}.${s}`; if (t(k) !== k) return t(k); }
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** An invoice period: "2026-10" stays as is, "HALL-7" (a community hall or amenity booking) reads "Hall booking 7". */
export function periodLabel(t: (k: string, v?: Record<string, string | number>) => string, period: string): string {
  return period.startsWith("HALL-") ? t("bill.hall", { n: period.slice(5) }) : period;
}
