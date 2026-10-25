import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Start your free trial", description: "30 days free, no card needed. Set up your building in an afternoon.", alternates: { canonical: "/signup" } };
export default function Layout({ children }: { children: ReactNode }) { return children; }
