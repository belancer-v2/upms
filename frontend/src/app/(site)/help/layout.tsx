import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Help center", description: "Short guides for every FlatWise screen, in English and Bangla.", alternates: { canonical: "/help" } };
export default function Layout({ children }: { children: ReactNode }) { return children; }
