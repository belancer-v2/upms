import type { Metadata } from "next";
import { headers } from "next/headers";
import type { ReactNode } from "react";
import "@fontsource-variable/nunito-sans";
import "@fontsource/hind-siliguri/400.css";
import "@fontsource/hind-siliguri/600.css";
import "@fontsource/hind-siliguri/700.css";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { LangProvider } from "@/lib/i18n";
import { ThemeProvider, themeBootScript } from "@/lib/theme";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || "https://flatwise.example"),
  title: { default: "FlatWise · Your building, in order.", template: "%s · FlatWise" },
  description: "Service charges, cash, expenses, notices and records for buildings in Bangladesh. Bangla and English.",
  applicationName: "FlatWise",
  icons: { icon: [{ url: "/brand/appicon.svg", type: "image/svg+xml" }], apple: "/apple-icon.png" },
  manifest: "/manifest.webmanifest",
  openGraph: { type: "website", siteName: "FlatWise", title: "FlatWise · Your building, in order.", description: "Service charges, cash, expenses, notices and records for buildings in Bangladesh.", locale: "en_BD", alternateLocale: ["bn_BD"] },
  twitter: { card: "summary_large_image", title: "FlatWise · Your building, in order.", description: "Service charges, cash, expenses, notices and records for buildings in Bangladesh." },
};

// Reading the per-request CSP nonce makes every page render on request (no static HTML), which a nonce-based policy requires.
export default async function RootLayout({ children }: { children: ReactNode }) {
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script nonce={nonce} dangerouslySetInnerHTML={{ __html: themeBootScript }} /></head>
      <body>
        <ThemeProvider><LangProvider><AuthProvider>{children}</AuthProvider></LangProvider></ThemeProvider>
      </body>
    </html>
  );
}
