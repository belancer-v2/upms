/** One place that decides which menu items each user type sees. Modules append their items here. */
export type NavItem = {
  key: string; href: string; icon: string; group: string;
  roles?: string[];   // customer roles (any of). Omit = every signed-in building user.
  saas?: string[];    // SaaS staff roles (any of). Omit = not shown to SaaS staff.
  anyone?: boolean;   // shown to everyone signed in
  feature?: string;   // the plan feature this item needs
};

export const COMMITTEE = ["PRESIDENT", "SECRETARY", "TREASURER", "MEMBER"];
export const MANAGERS = ["AGENCY_MANAGER", "PROPERTY_ADMIN"];
export const ALL_SAAS = ["SUPER_ADMIN", "SAAS_ADMIN", "SAAS_FINANCE", "SAAS_SALES", "SAAS_USER"];

export const NAV: NavItem[] = [
  { key: "nav.dashboard", href: "/app", icon: "home", group: "main", anyone: true },
  { key: "nav.saas.overview", href: "/app/saas", icon: "chart", group: "saas", saas: ALL_SAAS },
  { key: "nav.saas.buildings", href: "/app/saas/buildings", icon: "building", group: "saas", saas: ALL_SAAS },
  { key: "nav.saas.leads", href: "/app/saas/leads", icon: "inbox", group: "saas", saas: ["SUPER_ADMIN", "SAAS_ADMIN", "SAAS_SALES"] },
  { key: "nav.saas.invoices", href: "/app/saas/invoices", icon: "receipt", group: "saas", saas: ["SUPER_ADMIN", "SAAS_ADMIN", "SAAS_FINANCE"] },
  { key: "nav.saas.plans", href: "/app/saas/plans", icon: "tag", group: "saas", saas: ALL_SAAS },
  { key: "nav.saas.staff", href: "/app/saas/staff", icon: "users", group: "saas", saas: ["SUPER_ADMIN", "SAAS_ADMIN"] },
  { key: "nav.units", href: "/app/units", icon: "building", group: "building", roles: ["PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY", "TREASURER", "MEMBER", "AUDITOR", "CARETAKER", "GUARD"] },
  { key: "nav.people", href: "/app/people", icon: "users", group: "building", roles: ["PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY", "TREASURER", "MEMBER", "AUDITOR", "CARETAKER"] },
  { key: "nav.staff", href: "/app/staff", icon: "users", group: "people", roles: [...MANAGERS, "PRESIDENT", "SECRETARY", "TREASURER", "MEMBER", "AUDITOR"], feature: "staff" },
  { key: "nav.myflat", href: "/app/my-flat", icon: "home", group: "building", roles: ["FLAT_OWNER", "TENANT", "OWNER_REP"] },
  { key: "nav.portfolio", href: "/app/portfolio", icon: "chart", group: "building", roles: ["AGENCY_MANAGER"], saas: ["SUPER_ADMIN", "SAAS_ADMIN"] },
  { key: "nav.building", href: "/app/building", icon: "tag", group: "building", roles: ["PROPERTY_ADMIN", "AGENCY_MANAGER"] },
  { key: "nav.billing", href: "/app/billing", icon: "cash", group: "money", roles: [...MANAGERS, "PRESIDENT", "SECRETARY", "TREASURER", "MEMBER", "AUDITOR"], feature: "billing" },
  { key: "nav.finance", href: "/app/finance", icon: "chart", group: "money", roles: [...MANAGERS, "PRESIDENT", "SECRETARY", "TREASURER", "MEMBER", "AUDITOR", "CARETAKER"], feature: "expenses" },
  { key: "nav.cash", href: "/app/cash", icon: "cash", group: "money", roles: [...MANAGERS, "CARETAKER", "TREASURER"], feature: "caretaker_app" },
  { key: "nav.pay", href: "/app/pay", icon: "receipt", group: "money", roles: ["FLAT_OWNER", "TENANT", "OWNER_REP"], feature: "billing" },
  { key: "nav.messages", href: "/app/messages", icon: "mail", group: "comms", roles: [...MANAGERS, "PRESIDENT", "SECRETARY", "TREASURER", "AUDITOR"], feature: "reminders" },
  { key: "nav.roles", href: "/app/roles", icon: "shield", group: "system", anyone: true },
  { key: "nav.audit", href: "/app/audit", icon: "list", group: "system", roles: [...MANAGERS, "PRESIDENT", "AUDITOR"], saas: ["SUPER_ADMIN", "SAAS_ADMIN"] },
  { key: "nav.profile", href: "/app/profile", icon: "user", group: "system", anyone: true },
];

export const ICONS: Record<string, string> = {
  home: "M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10",
  shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  user: "M12 12a4 4 0 100-8 4 4 0 000 8zM4 21c0-4 4-6 8-6s8 2 8 6",
  building: "M4 21V5l8-2v18M12 9h8v12M7 9h2M7 13h2M7 17h2M15 13h2M15 17h2",
  money: "M3 7h18v10H3zM12 12m-2.5 0a2.5 2.5 0 105 0 2.5 2.5 0 10-5 0M6 10v.01M18 14v.01",
  users: "M9 11a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM2 20c0-3.5 3-5.5 7-5.5s7 2 7 5.5M17 4.5a3.5 3.5 0 010 6.5M22 20c0-2.6-1.7-4.4-4.5-5",
  bell: "M6 9a6 6 0 1112 0c0 6 2 7 2 7H4s2-1 2-7zM10 20a2 2 0 004 0",
  chart: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  tag: "M3 12V4h8l10 10-8 8L3 12zM7.5 8.5h.01",
  receipt: "M6 3h12v18l-3-2-3 2-3-2-3 2V3zM9 8h6M9 12h6",
  wrench: "M14.7 6.3a4 4 0 005 5L21 13l-8 8-3-3 8-8-1.3-1.7zM3 21l5-5",
  file: "M7 3h8l4 4v14H7zM15 3v4h4M10 12h6M10 16h6",
  card: "M3 6h18v12H3zM3 10h18",
  cash: "M3 7h18v10H3zM7 12h.01M17 12h.01M12 12m-3 0a3 3 0 106 0 3 3 0 10-6 0",
  box: "M3 7l9-4 9 4v10l-9 4-9-4V7zM3 7l9 4 9-4M12 11v10",
  gavel: "M14 4l6 6M3 21l9-9M9 7l6 6M6 10l5-5 4 4-5 5z",
  megaphone: "M3 11v2a1 1 0 001 1h3l8 4V6L7 10H4a1 1 0 00-1 1zM18 9a4 4 0 010 6",
  mail: "M3 5h18v14H3zM3 6l9 7 9-7",
  inbox: "M3 13l3-8h12l3 8v6H3zM3 13h5l1 3h6l1-3h5",
  star: "M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9L12 3z",
};
