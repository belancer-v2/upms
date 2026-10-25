"use client";
import { useEffect } from "react";
import { ErrorPanel } from "@/components/site/ErrorPanel";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { console.error(error); }, [error]);
  return <ErrorPanel kind="error" onRetry={reset} />;
}
