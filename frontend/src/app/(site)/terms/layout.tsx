import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Terms of Service", description: "The agreement between FlatWise and the buildings that use it.", alternates: { canonical: "/terms" } };
export default function Layout({ children }: { children: ReactNode }) { return children; }
