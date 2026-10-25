import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Questions and answers", description: "Answers about price, data, Bangla, payments, the free trial and privacy.", alternates: { canonical: "/faq" } };
export default function Layout({ children }: { children: ReactNode }) { return children; }
