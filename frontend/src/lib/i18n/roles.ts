export const rolesDict = {
  en: {
    "mod.saas": "SaaS console", "mod.leads": "Leads", "mod.saas_billing": "SaaS billing", "mod.property": "Property setup", "mod.billing": "Service charge",
    "mod.cash": "Cash collection", "mod.finance": "Finance", "mod.staff": "Staff and payroll", "mod.notices": "Notices and policies", "mod.tenant": "Tenant and DMP",
    "mod.complaints": "Complaints and committee", "mod.reports": "Reports",
  },
  bn: {
    "mod.saas": "সাস কনসোল", "mod.leads": "লিড", "mod.saas_billing": "সাস বিলিং", "mod.property": "প্রপার্টি সেটআপ", "mod.billing": "সার্ভিস চার্জ",
    "mod.cash": "নগদ সংগ্রহ", "mod.finance": "ফাইন্যান্স", "mod.staff": "স্টাফ ও বেতন", "mod.notices": "নোটিশ ও নীতিমালা", "mod.tenant": "ভাড়াটিয়া ও ডিএমপি",
    "mod.complaints": "অভিযোগ ও কমিটি", "mod.reports": "রিপোর্ট",
  },
} as const;

export const ROLE_MODULES: Record<string, string[]> = {
  SUPER_ADMIN: ["saas", "leads", "saas_billing", "property", "billing", "cash", "finance", "staff", "notices", "tenant", "complaints", "reports"],
  SAAS_ADMIN: ["saas", "property", "reports"],
  SAAS_FINANCE: ["saas_billing", "reports"],
  SAAS_SALES: ["leads", "saas"],
  SAAS_USER: ["property", "notices", "complaints"],
  AGENCY_MANAGER: ["property", "billing", "finance", "staff", "notices", "tenant", "complaints", "reports"],
  PROPERTY_ADMIN: ["property", "billing", "cash", "finance", "staff", "notices", "tenant", "complaints", "reports"],
  FLAT_OWNER: ["billing", "notices", "tenant", "complaints"],
  TENANT: ["billing", "notices", "complaints"],
  CARETAKER: ["cash", "complaints", "notices"],
  PRESIDENT: ["billing", "finance", "staff", "notices", "complaints", "reports"],
  SECRETARY: ["notices", "complaints", "reports"],
  TREASURER: ["billing", "cash", "finance", "reports"],
  MEMBER: ["billing", "notices", "complaints", "reports"],
  AUDITOR: ["billing", "finance", "reports"],
  GUARD: ["notices"],
  OWNER_REP: ["billing", "notices", "tenant", "complaints"],
};
export const SAAS_LIST = ["SUPER_ADMIN", "SAAS_ADMIN", "SAAS_FINANCE", "SAAS_SALES", "SAAS_USER"];
export const CUSTOMER_LIST = ["AGENCY_MANAGER", "PROPERTY_ADMIN", "FLAT_OWNER", "TENANT", "CARETAKER", "PRESIDENT", "SECRETARY", "TREASURER", "MEMBER", "AUDITOR", "GUARD", "OWNER_REP"];
