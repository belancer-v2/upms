import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Refund and Cancellation Policy", description: "How to cancel FlatWise and when you get money back.", alternates: { canonical: "/refund" } };
export default function Layout({ children }: { children: ReactNode }) { return children; }
