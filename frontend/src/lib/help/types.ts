/** Help center content is typed data: every article has English and Bangla, one language is shown at a time. */
export type L = { en: string; bn: string };
export type HelpGroup = "start" | "building" | "money" | "people" | "comms" | "life" | "reports" | "saas" | "data";

export const HELP_IDS = [
  "getting-started", "setup-wizard", "profile-language", "roles-access",
  "add-flats", "add-people", "building-details", "agency-portfolio", "my-flat",
  "charge-rules", "run-invoices", "verify-payments", "dues-reminders", "pay-service-charge", "cash-desk", "expenses-approvals", "ledger-basics", "budget-assets", "online-payments",
  "staff-registry", "payroll-eid", "agency-roster", "tenant-onboarding", "police-pack",
  "notices-read-proof", "policies-acceptance", "sms-email-credits",
  "raise-request", "handle-requests", "committee-meetings", "committee-votes", "visitor-gate", "visitor-resident", "hall-booking", "hall-admin", "parking", "rental-records",
  "building-reports", "audit-log",
  "saas-overview", "saas-plans", "saas-leads", "saas-invoices", "saas-credit-sales", "saas-email-campaigns", "saas-team", "saas-retention",
  "export-data", "account-deletion", "move-out-data",
] as const;
export type HelpId = (typeof HELP_IDS)[number];

export type Shot = { src: string; alt: L };
export type Article = {
  id: HelpId;
  group: HelpGroup;
  /** Customer roles and SaaS roles this article is written for. Drives the role badges and "recommended for you". */
  roles: string[];
  /** The screen the article explains. */
  route?: string;
  /** Plan feature the screen needs (same keys as the menu). */
  feature?: string;
  /** Lower comes first in "recommended". */
  rank: number;
  /** False for staff-only articles that the public site must not list. */
  public?: boolean;
  title: L;
  summary: L;
  steps: { en: string[]; bn: string[] };
  tips: { en: string[]; bn: string[] };
  /** Image slots. If the file is missing the page shows a neutral placeholder, so new screens can be added before their pictures. */
  shots?: Shot[];
  related?: HelpId[];
  /** Extra search words, both languages. */
  keywords?: string;
};

export const GROUP_ORDER: HelpGroup[] = ["start", "building", "money", "people", "comms", "life", "reports", "data", "saas"];

export const CUSTOMER_ROLES = ["AGENCY_MANAGER", "PROPERTY_ADMIN", "FLAT_OWNER", "TENANT", "CARETAKER", "PRESIDENT", "SECRETARY", "TREASURER", "MEMBER", "AUDITOR", "GUARD", "OWNER_REP"];
export const SAAS_ROLES = ["SUPER_ADMIN", "SAAS_ADMIN", "SAAS_FINANCE", "SAAS_SALES", "SAAS_USER"];
export const MGR = ["PROPERTY_ADMIN", "AGENCY_MANAGER"];
export const COM = ["PRESIDENT", "SECRETARY", "TREASURER", "MEMBER"];
export const RES = ["FLAT_OWNER", "TENANT", "OWNER_REP"];

/** Short author helper so each article reads as data. */
export function art(
  id: HelpId, group: HelpGroup, roles: string[], rank: number,
  meta: { route?: string; feature?: string; related?: HelpId[]; shots?: [string, string, string][]; keywords?: string; public?: boolean },
  en: { t: string; s: string; steps: string[]; tips: string[] },
  bn: { t: string; s: string; steps: string[]; tips: string[] },
): Article {
  return {
    id, group, roles, rank, route: meta.route, feature: meta.feature, related: meta.related, keywords: meta.keywords,
    public: meta.public ?? !roles.every((r) => SAAS_ROLES.includes(r)),
    title: { en: en.t, bn: bn.t }, summary: { en: en.s, bn: bn.s },
    steps: { en: en.steps, bn: bn.steps }, tips: { en: en.tips, bn: bn.tips },
    shots: meta.shots?.map(([name, altEn, altBn]) => ({ src: `/help/${name}.png`, alt: { en: altEn, bn: altBn } })),
  };
}
