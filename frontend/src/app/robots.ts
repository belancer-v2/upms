import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/company";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/app/", "/api/", "/pay/", "/t/", "/n/", "/unsubscribe/", "/login"] }],
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
