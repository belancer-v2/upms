import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/company";
import { ARTICLES } from "@/lib/help";

/** Public pages only. The app, the API, payment pages and token links are not listed. */
export default function sitemap(): MetadataRoute.Sitemap {
  const fixed: [string, number, MetadataRoute.Sitemap[number]["changeFrequency"]][] = [
    ["", 1, "weekly"], ["/features", 0.8, "monthly"], ["/pricing", 0.9, "weekly"], ["/demo", 0.7, "monthly"], ["/signup", 0.8, "monthly"], ["/faq", 0.6, "monthly"],
    ["/contact", 0.5, "yearly"], ["/help", 0.6, "monthly"], ["/terms", 0.3, "yearly"], ["/privacy", 0.3, "yearly"], ["/refund", 0.3, "yearly"],
  ];
  const help = ARTICLES.filter((a) => a.public !== false).map((a) => [`/help/${a.id}`, 0.4, "monthly"] as (typeof fixed)[number]);
  return [...fixed, ...help].map(([path, priority, changeFrequency]) => ({ url: `${SITE_URL}${path}`, changeFrequency, priority }));
}
