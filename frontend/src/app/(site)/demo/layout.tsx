import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Book a demo", description: "Tell us about your building and we will call you to set up a short demo.", alternates: { canonical: "/demo" } };
export default function Layout({ children }: { children: ReactNode }) { return children; }
