"use client";
import { useEffect, useState } from "react";

/** Last resort when the root layout itself failed: no providers are available, so this page is self-contained and brand coloured. */
export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const [bn, setBn] = useState(false);
  useEffect(() => { try { setBn(localStorage.getItem("fw_lang") === "bn"); } catch { /* storage blocked */ } }, []);
  return (
    <html lang={bn ? "bn" : "en"}>
      <body style={{ margin: 0, minHeight: "100vh", display: "grid", placeItems: "center", background: "#F7F3F3", color: "#2A1520", fontFamily: "system-ui, sans-serif", padding: 24 }}>
        <div style={{ maxWidth: 520, textAlign: "center", background: "#fff", border: "1.5px solid #ECE6E6", borderRadius: 18, padding: "36px 28px" }}>
          <div style={{ fontSize: 64, fontWeight: 900, color: "#9D1E5F", lineHeight: 1 }}>!</div>
          <h1 style={{ fontSize: 24 }}>{bn ? "কিছু একটা ভুল হয়েছে" : "Something went wrong"}</h1>
          <p style={{ color: "#6D6E70" }}>{bn ? "এটি আপনার দোষ নয়। আবার চেষ্টা করুন।" : "It is not you. Please try again."}</p>
          <button onClick={reset} style={{ background: "#9D1E5F", color: "#fff", border: 0, borderRadius: 14, padding: "12px 22px", fontWeight: 800, fontSize: 16, cursor: "pointer" }}>{bn ? "আবার চেষ্টা করুন" : "Try again"}</button>
        </div>
      </body>
    </html>
  );
}
