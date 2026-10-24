"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/auth";

// Replaced by the landing website in M1.
export default function Home() {
  const { ready, user } = useAuth(); const r = useRouter();
  useEffect(() => { if (ready) r.replace(user ? "/app" : "/login"); }, [ready, user, r]);
  return null;
}
