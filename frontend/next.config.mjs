const API = process.env.API_ORIGIN || process.env.API_URL || "http://127.0.0.1:8000";
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone", // self-contained server for cPanel Node.js App and Docker
  // NEXT_DIST_DIR lets a second instance build to its own folder without touching the main one.
  ...(process.env.NEXT_DIST_DIR ? { distDir: process.env.NEXT_DIST_DIR } : {}),
  poweredByHeader: false, // do not announce the framework (P2)
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
  // Security headers for every page (P2). The Content-Security-Policy is set per request in src/middleware.ts because it carries a nonce.
  async headers() {
    const prod = process.env.NODE_ENV === "production";
    const common = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()" },
      { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
      ...(prod ? [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }] : []),
    ];
    return [
      { source: "/:path*", headers: [...common, { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" }] },
      // pages whose address carries a secret (SMS links, reset and confirmation links, payment sessions): never send it as a referrer
      { source: "/:area(n|t|unsubscribe|pay|reset-password|verify-email)/:rest*", headers: [{ key: "Referrer-Policy", value: "no-referrer" }] },
    ];
  },
};
export default nextConfig;
