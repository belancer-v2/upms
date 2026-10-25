/** Suggested monthly charges for a Bangladeshi apartment building. Amounts are BDT; "sqft" means BDT per square foot. The owner edits them in the wizard. */
export type ChargeDefault = { key: string; name: string; name_bn: string; kind: "flat" | "per_sqft"; bdt: number; on: boolean };

export const CHARGE_DEFAULTS: ChargeDefault[] = [
  { key: "service", name: "Service charge", name_bn: "সার্ভিস চার্জ", kind: "per_sqft", bdt: 3, on: true },
  { key: "security", name: "Security", name_bn: "নিরাপত্তা", kind: "flat", bdt: 500, on: true },
  { key: "cleaning", name: "Cleaning", name_bn: "পরিচ্ছন্নতা", kind: "flat", bdt: 300, on: true },
  { key: "lift", name: "Lift maintenance", name_bn: "লিফট রক্ষণাবেক্ষণ", kind: "flat", bdt: 400, on: true },
  { key: "generator", name: "Generator fuel", name_bn: "জেনারেটর জ্বালানি", kind: "flat", bdt: 300, on: false },
  { key: "water", name: "Water pump and common electricity", name_bn: "পানির পাম্প ও কমন বিদ্যুৎ", kind: "flat", bdt: 200, on: false },
  { key: "sinking", name: "Sinking fund", name_bn: "সঞ্চিতি তহবিল", kind: "per_sqft", bdt: 1, on: false },
];

export const REMINDER_STEPS = ["before", "due", "o7", "o15", "o30"] as const;
export const REMINDER_KEY: Record<(typeof REMINDER_STEPS)[number], string> = { before: "su.r.before", due: "su.r.dueday", o7: "su.r.o7", o15: "su.r.o15", o30: "su.r.o30" };
export const SETUP_STEPS = ["building", "flats", "charges", "reminders", "committee", "review"] as const;
export type SetupStep = (typeof SETUP_STEPS)[number];

export type SetupState = {
  applicable: boolean; completed: boolean; dismissed: boolean; percent: number; next_step: SetupStep | null;
  steps: { step: SetupStep; state: "done" | "skipped" | "known" | "todo" }[];
  data: { due_day?: number; reminders?: { enabled: boolean; steps: string[] } };
  known: { building: { name: string; name_bn: string; address: string; city: string; floors: number }; units: number; rules: number; committee: number; due_day: number | null };
  features: string[];
};
