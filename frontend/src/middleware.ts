import { NextResponse, type NextRequest } from "next/server";

/**
 * Content-Security-Policy with a fresh nonce on every page request (P2).
 *
 * Next.js reads the nonce from the request's CSP header and stamps it on its own inline scripts; the layout reads `x-nonce` for the theme
 * boot script. `strict-dynamic` lets those trusted scripts load the rest, so there is no 'unsafe-inline' for scripts and no allow-list of hosts.
 * Styles keep 'unsafe-inline' because React renders style="" attributes all over the app, which cannot carry a nonce; that is a much smaller risk than scripts.
 * Everything else is same-origin: the API is reached through the /api rewrite, fonts and images are bundled, nothing is loaded from a CDN.
 *
 * CSP_REPORT_ONLY=1 sends the policy as Content-Security-Policy-Report-Only (browsers log violations but block nothing): use it for a first rollout.
 */
export function middleware(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID());
  const dev = process.env.NODE_ENV !== "production";
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' blob: data: https:",   // https: so the e-mail template preview (a sandboxed srcdoc frame that inherits this policy) can show remote images
    "font-src 'self' data:",
    `connect-src 'self'${dev ? " ws: wss:" : ""}`,
    "media-src 'self' blob:",
    "object-src 'none'",
    "frame-src 'none'",
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
  const header = process.env.CSP_REPORT_ONLY === "1" ? "Content-Security-Policy-Report-Only" : "Content-Security-Policy";

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set(header, csp);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set(header, csp);
  return response;
}

export const config = {
  // pages only: not the API (the backend sets its own CSP), static assets, images, or files with an extension
  matcher: [{ source: "/((?!api/|_next/static|_next/image|brand/|.*\\..*).*)", missing: [{ type: "header", key: "next-router-prefetch" }, { type: "header", key: "purpose", value: "prefetch" }] }],
};
