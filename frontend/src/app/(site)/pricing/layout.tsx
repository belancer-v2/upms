import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Pricing", description: "Simple monthly or yearly prices per building, in BDT. 30-day free trial, no card needed.", alternates: { canonical: "/pricing" } };
export default function Layout({ children }: { children: ReactNode }) { return children; }
