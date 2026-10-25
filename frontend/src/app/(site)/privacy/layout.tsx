import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Privacy Policy", description: "What personal data FlatWise handles, why, and your choices. No advertising or tracking cookies.", alternates: { canonical: "/privacy" } };
export default function Layout({ children }: { children: ReactNode }) { return children; }
