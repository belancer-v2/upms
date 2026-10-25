/**
 * Company details that the OWNER must fill in before launch. Everything in [SQUARE BRACKETS] is a placeholder:
 * it is shown highlighted on the legal pages, the contact page and the help center, so it cannot be missed.
 * Search for "[" in this file to find every one. See docs/LAUNCH_CHECKLIST.md.
 */
export type Bi = { en: string; bn: string };

export const COMPANY: Record<string, Bi> = {
  legalName: { en: "[COMPANY LEGAL NAME]", bn: "[কোম্পানির আইনি নাম]" },
  address: { en: "[REGISTERED ADDRESS, CITY, BANGLADESH]", bn: "[নিবন্ধিত ঠিকানা, শহর, বাংলাদেশ]" },
  jurisdiction: { en: "[CITY] courts, Bangladesh", bn: "[শহর]-এর আদালত, বাংলাদেশ" },
  tradeLicence: { en: "[TRADE LICENCE NUMBER]", bn: "[ট্রেড লাইসেন্স নম্বর]" },
  bin: { en: "[BIN / TIN]", bn: "[বিআইএন / টিআইএন]" },
  supportEmail: { en: "[SUPPORT EMAIL]", bn: "[সাপোর্ট ইমেইল]" },
  supportPhone: { en: "[SUPPORT PHONE]", bn: "[সাপোর্ট ফোন]" },
  supportHours: { en: "[SUPPORT HOURS, for example Sat to Thu, 9:00 to 18:00]", bn: "[সাপোর্টের সময়, যেমন শনি থেকে বৃহস্পতি, সকাল ৯টা থেকে সন্ধ্যা ৬টা]" },
  privacyEmail: { en: "[PRIVACY CONTACT EMAIL]", bn: "[গোপনীয়তা যোগাযোগের ইমেইল]" },
  website: { en: "[WEBSITE ADDRESS]", bn: "[ওয়েবসাইটের ঠিকানা]" },
};
/** Date the legal texts were last drafted. Update it when you change them. */
export const LEGAL_UPDATED = "2026-10-25";
/** Canonical site address used for the sitemap, robots.txt and social previews. Set NEXT_PUBLIC_SITE_URL in the environment. */
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || "https://flatwise.example").replace(/\/$/, "");
/** Set to true once a lawyer has reviewed lib/legal.ts and the placeholders above are filled. Until then the legal pages show a "draft" notice. */
export const LEGAL_REVIEWED = false;
