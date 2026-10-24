import type { Metadata } from "next";
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
  title: "FlatWise · Your building, in order.",
  description: "Service charges, cash, expenses, notices and records for buildings in Bangladesh.",
  icons: { icon: "/brand/appicon.svg" },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeBootScript }} /></head>
      <body>
        <ThemeProvider><LangProvider><AuthProvider>{children}</AuthProvider></LangProvider></ThemeProvider>
      </body>
    </html>
  );
}
