import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Contact", description: "Talk to the FlatWise team about your building.", alternates: { canonical: "/contact" } };
export default function Layout({ children }: { children: ReactNode }) { return children; }
