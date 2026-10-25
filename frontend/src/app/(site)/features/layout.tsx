import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Features", description: "Service charge, cash with proof, expenses, notices, staff, tenant onboarding and more, made for buildings in Bangladesh.", alternates: { canonical: "/features" } };
export default function Layout({ children }: { children: ReactNode }) { return children; }
