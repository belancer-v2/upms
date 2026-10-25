#!/usr/bin/env node
// Per-role UX sweep. Logs in as every demo role, opens EVERY item in that role's sidebar and records problems.
//
//   node scripts/sweep.cjs                       all roles, all modes (WEB=http://127.0.0.1:3000 API=http://127.0.0.1:8000)
//   WEB=http://127.0.0.1:3100 API=http://127.0.0.1:8100 node scripts/sweep.cjs --roles guard,caretaker --modes mobile
//
// Options: --roles a,b   --modes en-light,bn-dark,mobile,bn-mobile   --workers 4   --out docs/SWEEP_REPORT   --shots <dir>   --extra (also visit detail pages)
// Uses the globally installed Playwright with the preinstalled Chromium (never runs `playwright install`).
// Writes <out>.json and <out>.md. Exit code 1 when there are open issues that are not listed in KNOWN.
const fs = require("fs");
const path = require("path");
const cp = require("child_process");
const ROOT = path.join(__dirname, "..");
const WEB = (process.env.WEB || "http://127.0.0.1:3000").replace(/\/$/, "");
const API = (process.env.API || "http://127.0.0.1:8000").replace(/\/$/, "");
const argv = process.argv.slice(2);
const opt = (name, def) => { const i = argv.indexOf(`--${name}`); return i >= 0 && argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[i + 1] : def; };
const flag = (name) => argv.includes(`--${name}`);

let chromium;
try { chromium = require("playwright").chromium; }
catch { chromium = require(path.join(cp.execSync("npm root -g").toString().trim(), "playwright")).chromium; }

const ROLES = ["super", "admin", "finance", "sales", "support", "agency", "padmin", "owner", "owner2", "tenant", "caretaker", "guard", "president", "secretary", "treasurer", "member", "auditor", "ownerrep"];
const MODES = {
  "en-light": { lang: "en", theme: "light", w: 1440, h: 900 },
  "bn-dark": { lang: "bn", theme: "dark", w: 1440, h: 900 },
  "mobile": { lang: "en", theme: "light", w: 390, h: 844, mobile: true },
  "bn-mobile": { lang: "bn", theme: "light", w: 390, h: 844, mobile: true },
};
const roles = (opt("roles", "") || "").split(",").filter(Boolean);
const modes = (opt("modes", "en-light,bn-dark,mobile") || "").split(",").filter(Boolean);
const workers = parseInt(opt("workers", "4"), 10);
const OUT = path.resolve(ROOT, opt("out", "docs/SWEEP_REPORT"));
const SHOTS = opt("shots", "");
const pickRoles = roles.length ? roles : ROLES;

// Known and documented items: matched against `${kind} ${path} ${detail}`. Anything matching is reported under "Known" and does not fail the run.
const KNOWN = [
  { re: /^uncaught-exception \/app React error #418|^uncaught-exception \/app Minified React error #418/, why: "Rare hydration warning on /app under parallel load (2 of 108 loads; 0 of 32 sequential loads). In development React only reports the nonce attribute of the root layout's inline theme script, which belongs to the security work on the root layout." },
];

// ---------------------------------------------------------------- in-page checks (run inside the browser)
function inPage(args) {
  const { lang, mobile, strictTap } = args;
  const dataWords = new Set(args.dataWords || []);   // words that came from the API (names, titles, notes): content, not interface labels
  const out = [];
  const vis = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none" && cs.opacity !== "0"; };
  const inHiddenNav = (el) => !!el.closest("aside.sidebar:not(.open)") && window.innerWidth <= 960;
  const short = (el) => (el.tagName.toLowerCase() + (el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".") : "") + " \"" + (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 40) + "\"");
  // 1. horizontal overflow of the page
  const de = document.documentElement;
  if (de.scrollWidth > window.innerWidth + 2) {
    const bad = [];
    for (const el of document.querySelectorAll("body *")) {
      if (inHiddenNav(el) || !vis(el)) continue;
      if (el.closest(".table-wrap, pre, .no-scroll-check")) continue;
      const r = el.getBoundingClientRect();
      if (r.right > window.innerWidth + 2 && r.width < window.innerWidth * 3) bad.push(short(el) + ` right=${Math.round(r.right)}`);
      if (bad.length >= 3) break;
    }
    out.push({ kind: "overflow-x", detail: `scrollWidth ${de.scrollWidth} > ${window.innerWidth}; ${bad.join(" | ")}` });
  }
  // 2. clipped text in buttons, chips and tabs
  let clipped = 0;
  for (const el of document.querySelectorAll("button, .btn, .chip, .tab, a.btn, select")) {
    if (!vis(el) || inHiddenNav(el)) continue;
    const cs = getComputedStyle(el);
    const rng = document.createRange(); rng.selectNodeContents(el);
    const tr = rng.getBoundingClientRect(); const br = el.getBoundingClientRect();
    const spill = el.tagName === "SELECT" ? false : (tr.width > br.width + 2 && (cs.whiteSpace === "nowrap" || cs.overflow !== "visible")) || (el.scrollWidth > el.clientWidth + 2 && cs.overflowX !== "visible" && cs.overflowX !== "auto");
    const clipY = el.scrollHeight > el.clientHeight + 3 && cs.overflowY === "hidden";
    if ((spill || clipY) && clipped++ < 4) out.push({ kind: "clipped-text", detail: short(el) });
  }
  // 3. empty screen / stuck loading
  const main = document.querySelector("main.content") || document.body;
  const txt = (main.innerText || "").trim();
  const loadingWords = lang === "bn" ? ["লোড হচ্ছে"] : ["Loading"];
  if (txt.length < 30) out.push({ kind: "empty-screen", detail: `only ${txt.length} characters: "${txt.replace(/\s+/g, " ")}"` });
  else if (loadingWords.some((w) => txt.includes(w)) && txt.length < 120) out.push({ kind: "stuck-loading", detail: txt.replace(/\s+/g, " ").slice(0, 80) });
  // 4. untranslated key strings, and language mixing
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const keyRe = /^[a-z]+\.[a-z_.]+$/;
  const latinAllow = /^(Sept|January|February|March|April|June|July|August|September|October|November|December|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|ZIP|BDT|SMS|OTP|NID|PDF|CSV|FlatWise|UPMS|bKash|Nagad|MRR|ARR|VAT|TIN|BIN|CCTV|AMC|DESCO|WASA|EN|AM|PM|GB|MB|KB|JPG|PNG|SQ|FT|QR|URL|ID|Wi-Fi|DBBL|Mon|Tue|Wed|Thu|Fri|Sat|Sun|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$/i;
  const seenKey = new Set(); const mixed = []; let keyCount = 0; let moneyBad = 0;
  while (walker.nextNode()) {
    const n = walker.currentNode; const el = n.parentElement;
    if (!el || /^(SCRIPT|STYLE|NOSCRIPT|OPTION|TEXTAREA|CODE)$/.test(el.tagName) || !vis(el) || inHiddenNav(el)) continue;
    const t = n.textContent.trim();
    if (!t) continue;
    if (keyRe.test(t) && !seenKey.has(t)) { seenKey.add(t); if (keyCount++ < 6) out.push({ kind: "untranslated-key", detail: `"${t}" in ${short(el.closest("div, td, li, button, a, label, h1, h2, h3") || el)}` }); }
    if (!(t.match(/[ঀ-৿]+/g) || []).every((w) => dataWords.has(w)) && /৳|BDT\s*[০-৯]|[০-৯][০-৯,.]*\s*(টাকা|BDT)/.test(t) && moneyBad++ < 4) out.push({ kind: "money-format", detail: `"${t.slice(0, 70)}": money must be BDT with Latin digits` });
    if (!(t.match(/[ঀ-৿]+/g) || []).every((w) => dataWords.has(w)) && /[০-৯]{1,2}\s*(জানুয়ারি|ফেব্রুয়ারি|মার্চ|এপ্রিল|জুন|জুলাই|আগস্ট|সেপ্টেম্বর|অক্টোবর|নভেম্বর|ডিসেম্বর)/.test(t) && moneyBad++ < 4) out.push({ kind: "date-format", detail: `"${t.slice(0, 70)}": dates must be en-GB (25 Oct 2026)` });
    if (el.closest("[data-keep-lang], .keep-lang, .avatar, pre") || t === "বাংলা" || t === "English") continue;   // language names are written in their own script
    if (lang === "bn") {
      const words = (t.replace(/[0-9][0-9.,:\-/]*/g, " ").match(/[A-Za-z][A-Za-z'’\-]{2,}/g) || []).filter((w) => !latinAllow.test(w) && !/^[A-Z0-9-]+$/.test(w) && !dataWords.has(w.toLowerCase()));
      if (words.length && mixed.length < 8) mixed.push(`${words.slice(0, 4).join(" ")}  [${short(el).slice(0, 50)}]`);
    } else if ((t.match(/[ঀ-৿]+/g) || []).some((w) => !dataWords.has(w)) && mixed.length < 8) mixed.push(`${t.slice(0, 40)}  [${short(el).slice(0, 50)}]`);
  }
  for (const m of mixed.slice(0, 6)) out.push({ kind: lang === "bn" ? "english-in-bangla" : "bangla-in-english", detail: m });
  // placeholders / titles / aria-labels that are keys
  for (const el of document.querySelectorAll("[placeholder], [title], [aria-label]")) {
    for (const a of ["placeholder", "title", "aria-label"]) {
      const v = el.getAttribute(a); if (v && keyRe.test(v.trim()) && vis(el)) out.push({ kind: "untranslated-key", detail: `${a}="${v}" on ${short(el)}` });
    }
  }
  // 5. form controls without a label
  let unl = 0;
  for (const el of document.querySelectorAll("input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea")) {
    if (!vis(el) || inHiddenNav(el) || el.closest(".modal-bg") === null && false) continue;
    const labelled = el.getAttribute("aria-label") || el.getAttribute("aria-labelledby") || (el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`)) || el.closest("label") || el.getAttribute("title");
    if (!labelled && unl++ < 4) out.push({ kind: "unlabelled-control", detail: short(el) + ` placeholder="${el.getAttribute("placeholder") || ""}"` });
  }
  let unlc = 0;
  for (const el of document.querySelectorAll("input[type=checkbox], input[type=radio]")) {
    if (!vis(el) || el.hidden || inHiddenNav(el)) continue;
    const labelled = el.getAttribute("aria-label") || el.closest("label") || (el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`));
    if (!labelled && unlc++ < 3) out.push({ kind: "unlabelled-control", detail: short(el) });
  }
  // 6. icon buttons without a name
  let nm = 0;
  for (const el of document.querySelectorAll("button, a[href], [role=button]")) {
    if (!vis(el) || inHiddenNav(el)) continue;
    const name = (el.innerText || "").trim() || el.getAttribute("aria-label") || el.getAttribute("title") || el.querySelector("img[alt]:not([alt=''])");
    if (!name && nm++ < 3) out.push({ kind: "unnamed-control", detail: short(el) + " " + el.outerHTML.slice(0, 80) });
  }
  // 7. tap targets on a phone (44px). Always counted; only an issue for the roles that work on their feet
  if (mobile) {
    const small = [];
    for (const el of document.querySelectorAll("button, a[href], input:not([type=hidden]), select, textarea, [role=tab], summary")) {
      if (!vis(el) || inHiddenNav(el)) continue;
      if (el.tagName === "INPUT" && (el.type === "checkbox" || el.type === "radio")) { const l = el.closest("label"); const r = (l || el).getBoundingClientRect(); if (r.height >= 44 || el.hidden) continue; small.push(short(l || el) + ` ${Math.round(r.width)}x${Math.round(r.height)}`); continue; }
      if (el.tagName === "A" && el.closest("p, li, span, td, .small, .muted") && !el.className) continue;   // links inside a sentence follow WCAG's inline exception
      const r = el.getBoundingClientRect();
      if (r.height < 43.5 || r.width < 43.5 && !(el.tagName === "INPUT" || el.tagName === "SELECT")) small.push(short(el) + ` ${Math.round(r.width)}x${Math.round(r.height)}`);
    }
    if (small.length) out.push({ kind: strictTap ? "small-tap-target" : "info-small-tap-target", detail: `${small.length}: ${small.slice(0, 4).join(" | ")}` });
  }
  return out;
}

// ---------------------------------------------------------------- driver
async function login(role) {
  const r = await fetch(`${API}/api/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: `${role}@flatwise.demo`, password: "demo1234" }) });
  if (!r.ok) throw new Error(`login ${role}: ${r.status} ${await r.text()}`);
  return r.json();
}

async function sweepRole(browser, role, modeName, report) {
  const mode = MODES[modeName];
  let auth;
  try { auth = await login(role); } catch (e) { report.push({ role, mode: modeName, path: "(login)", kind: "login-failed", detail: String(e.message).slice(0, 200) }); return { pages: 0 }; }
  const prop = auth.properties.find((p) => p.name === "Sunrise Tower") || auth.properties[0];
  const ctx = await browser.newContext({ viewport: { width: mode.w, height: mode.h }, deviceScaleFactor: 1, isMobile: !!mode.mobile, hasTouch: !!mode.mobile, acceptDownloads: true });
  await ctx.addInitScript(([t, p, l, th]) => { try { localStorage.setItem("fw_token", t); if (p) localStorage.setItem("fw_prop", String(p)); localStorage.setItem("fw_lang", l); localStorage.setItem("fw_theme", th); } catch (e) {} }, [auth.token, prop ? prop.id : 0, mode.lang, mode.theme]);
  const page = await ctx.newPage();
  page.on("dialog", (d) => d.dismiss().catch(() => {}));
  let cur = { path: "" }; let pending = []; const dataWords = new Set();
  const push = (kind, detail) => pending.push({ role, mode: modeName, path: cur.path, kind, detail });
  page.on("pageerror", (e) => push("uncaught-exception", String(e.message || e).slice(0, 240)));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource|favicon/.test(m.text())) push("console-error", m.text().slice(0, 240)); });
  const harvest = (v) => { if (typeof v === "string") { for (const w of v.toLowerCase().match(/[a-z][a-z'’\-]{2,}/g) || []) dataWords.add(w); for (const w of v.match(/[ঀ-৿]+/g) || []) dataWords.add(w); } else if (Array.isArray(v)) v.forEach(harvest); else if (v && typeof v === "object") Object.values(v).forEach(harvest); };
  page.on("response", async (r) => {
    try { const u0 = new URL(r.url()); if (u0.pathname.startsWith("/api/") && r.status() < 400 && /json/.test(r.headers()["content-type"] || "")) harvest(await r.json()); } catch {}
    const s = r.status(); if (s < 400) return;
    const u = new URL(r.url()); if (!u.pathname.startsWith("/api/") && !u.pathname.startsWith("/_next")) return;
    const row = `${r.request().method()} ${u.pathname}${u.search.slice(0, 40)} -> ${s}`;
    push(s === 402 || s === 403 ? "gated-4xx" : s >= 500 ? "server-error" : "failed-request", row);
  });
  page.on("requestfailed", (r) => { const f = r.failure(); if (f && !/ERR_ABORTED/.test(f.errorText)) push("request-failed", `${r.method()} ${new URL(r.url()).pathname} ${f.errorText}`); });

  const visit = async (p) => {
    cur = { path: p }; pending = [];
    try { await page.goto(WEB + p, { waitUntil: "networkidle", timeout: 30000 }); } catch (e) { push("navigation-timeout", String(e.message).slice(0, 120)); }
    await page.waitForTimeout(700);
    let found = [];
    try { found = await page.evaluate(inPage, { lang: mode.lang, mobile: !!mode.mobile, strictTap: role === "guard" || role === "caretaker", dataWords: Array.from(dataWords) }); } catch (e) { push("check-failed", String(e.message).slice(0, 120)); }
    for (const f of found) push(f.kind, f.detail);
    // every tab of the page too (tabs hold most of the screens: money, people, settings)
    const nTabs = Math.min(await page.locator('main [role="tab"]').count().catch(() => 0), 10);
    const basePath = cur.path;
    for (let i = 0; i < nTabs; i++) {
      try {
        const tab = page.locator('main [role="tab"]').nth(i);
        if ((await tab.getAttribute("aria-selected")) === "true") continue;
        await tab.click({ timeout: 4000 }); await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {}); await page.waitForTimeout(450);
        const label = ((await tab.innerText().catch(() => "")) || `#${i}`).replace(/\s+/g, " ").slice(0, 24);
        cur = { path: `${basePath} [tab ${label}]` };
        const more = await page.evaluate(inPage, { lang: mode.lang, mobile: !!mode.mobile, strictTap: role === "guard" || role === "caretaker", dataWords: Array.from(dataWords) });
        for (const f of more) push(f.kind, f.detail);
        cur = { path: basePath };
      } catch (e) { cur = { path: basePath }; }
    }
    // forms that open in a dialog: press the page's "add / new / record" style buttons (never run/send/pay/approve/delete) and check the dialog too
    if (!flag("no-modals")) {
      const SAFE = /^(add|new|create|request|record|log|upload|edit|invite|schedule|book|raise|register|import|যোগ|নতুন|তৈরি|অনুরোধ|লিখু|আপলোড|সম্পাদনা|নিবন্ধন|বুক|আমদানি)/i;
      const NOT = /(run|send|pay|approve|delete|remove|sign|logout|out|reject|cancel|confirm|void|suspend|publish|মুছ|পাঠান|পরিশোধ|অনুমোদন|বাতিল|নাকচ|সাইন)/i;
      const btns = page.locator("main .btn-primary, main .btn-soft, main .btn-outline");
      const n = Math.min(await btns.count().catch(() => 0), 8); const tried = new Set(); let opened = 0;
      for (let i = 0; i < n && opened < 3; i++) {
        try {
          const b = btns.nth(i); if (!(await b.isVisible())) continue;
          const label = ((await b.innerText()) || "").replace(/\s+/g, " ").trim();
          if (!label || tried.has(label) || !SAFE.test(label) || NOT.test(label)) continue;
          tried.add(label); await b.click({ timeout: 3000 }); await page.waitForTimeout(500);
          if (await page.locator(".modal").count()) {
            opened++; cur = { path: `${basePath} [dialog ${label.slice(0, 24)}]` };
            const more = await page.evaluate(inPage, { lang: mode.lang, mobile: !!mode.mobile, strictTap: role === "guard" || role === "caretaker", dataWords: Array.from(dataWords) });
            for (const f of more) push(f.kind, f.detail);
            cur = { path: basePath };
            await page.keyboard.press("Escape"); await page.waitForTimeout(250);
            if (await page.locator(".modal").count()) push("dialog-not-closed-by-escape", label);
          } else if (page.url() !== WEB + basePath) { await page.goto(WEB + basePath, { waitUntil: "networkidle", timeout: 30000 }).catch(() => {}); }
        } catch (e) { cur = { path: basePath }; await page.keyboard.press("Escape").catch(() => {}); }
      }
    }
    const real = pending.filter((x) => !/^(gated-4xx|info-)/.test(x.kind));
    if (SHOTS && real.length) { try { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, `${role}-${modeName}-${p.replace(/[^a-z0-9]+/gi, "_")}.png`), fullPage: false }); } catch {} }
    report.push(...pending);
  };

  await visit("/app");
  const links = await page.evaluate(() => Array.from(document.querySelectorAll("aside.sidebar nav a")).map((a) => a.getAttribute("href")));
  const paths = Array.from(new Set(links.filter(Boolean)));
  if (!paths.length) report.push({ role, mode: modeName, path: "/app", kind: "no-nav", detail: "the sidebar has no links" });
  for (const p of paths) if (p !== "/app") await visit(p);
  if (flag("extra")) for (const p of (EXTRA[role] || [])) await visit(p);
  await ctx.close();
  return { pages: paths.length, property: prop ? prop.name : "", nav: paths };
}
const EXTRA = {
  super: ["/app/saas/buildings/2", "/app/saas/mail/templates/1", "/app/saas/invoice/1"],
  padmin: ["/app/payslip/1", "/app/receipt/1", "/app/onboarding/1/pack"],
};

(async () => {
  const browser = await chromium.launch();
  const jobs = [];
  for (const m of modes) { if (!MODES[m]) throw new Error(`unknown mode ${m}`); for (const r of pickRoles) jobs.push({ role: r, mode: m }); }
  const report = []; const summary = {}; let next = 0; const t0 = Date.now();
  await Promise.all(Array.from({ length: Math.min(workers, jobs.length) }, async () => {
    while (next < jobs.length) {
      const j = jobs[next++]; const mine = [];
      try { const s = await sweepRole(browser, j.role, j.mode, mine); summary[`${j.role}|${j.mode}`] = s; }
      catch (e) { mine.push({ role: j.role, mode: j.mode, path: "(sweep)", kind: "sweep-crashed", detail: String(e.message).slice(0, 200) }); summary[`${j.role}|${j.mode}`] = { pages: 0 }; }
      report.push(...mine); process.stderr.write(`done ${j.role} ${j.mode} (${summary[`${j.role}|${j.mode}`].pages} pages, ${mine.filter((x) => !/^(gated-4xx|info-)/.test(x.kind)).length} findings)\n`);
    }
  }));
  await browser.close();

  // ---- classify, de-duplicate
  const known = (x) => KNOWN.find((k) => k.re.test(`${x.kind} ${x.path} ${x.detail}`));
  const seen = new Set(); const items = [];
  for (const x of report) { const key = `${x.role}|${x.mode}|${x.path}|${x.kind}|${x.detail}`; if (seen.has(key)) continue; seen.add(key); items.push({ ...x, known: known(x)?.why || "" }); }
  const gated = items.filter((x) => x.kind === "gated-4xx"); const info = items.filter((x) => x.kind.startsWith("info-"));
  const open = items.filter((x) => x.kind !== "gated-4xx" && !x.kind.startsWith("info-") && !x.known);
  const documented = items.filter((x) => x.known);
  const count = (arr, f) => arr.reduce((m, x) => ((m[f(x)] = (m[f(x)] || 0) + 1), m), {});
  const result = { generated: new Date().toISOString(), web: WEB, api: API, roles: pickRoles, modes, seconds: Math.round((Date.now() - t0) / 1000), summary, counts: count(open, (x) => x.kind), open, documented, gated, info };
  fs.writeFileSync(OUT + ".json", JSON.stringify(result, null, 1));

  const md = [];
  md.push(`# Sweep report`, "", `Generated ${result.generated} against ${WEB} (API ${API}). ${pickRoles.length} roles x ${modes.length} modes, ${result.seconds}s.`, "",
    `Every item of each role's sidebar was opened (building: Sunrise Tower) in: ${modes.map((m) => `${m} (${MODES[m].w}px, ${MODES[m].lang.toUpperCase()}, ${MODES[m].theme})`).join("; ")}.`, "",
    "Checked per page: console errors, uncaught exceptions, failed requests (402/403 are listed as gated, not counted), horizontal page overflow, clipped text in buttons/chips/tabs, empty or stuck-loading screens, untranslated key strings, English text on Bangla screens and Bangla on English screens, controls without labels, controls without a name, and tap targets under 44px on the phone viewport (an issue for guard and caretaker; informational for the rest).", "");
  md.push(`## Result`, "", open.length ? `**${open.length} open finding(s)**: ${Object.entries(result.counts).map(([k, v]) => `${k} ${v}`).join(", ")}.` : "**No open findings.**", "");
  md.push(`| Role | Mode | Pages | Open findings |`, `|---|---|---|---|`);
  for (const [k, v] of Object.entries(summary).sort()) { const [r, m] = k.split("|"); md.push(`| ${r} | ${m} | ${v.pages} | ${open.filter((x) => x.role === r && x.mode === m).length} |`); }
  const group = (arr, title) => {
    if (!arr.length) return;
    md.push("", `## ${title} (${arr.length})`, "");
    const by = {}; for (const x of arr) (by[x.kind] ||= []).push(x);
    for (const [k, list] of Object.entries(by)) {
      md.push(`### ${k} (${list.length})`, "");
      const byPath = {}; for (const x of list) (byPath[`${x.path} :: ${x.detail}`] ||= []).push(`${x.role}/${x.mode}`);
      for (const [pd, who] of Object.entries(byPath).slice(0, 60)) md.push(`- \`${pd.slice(0, 300)}\` (${who.length > 4 ? who.slice(0, 4).join(", ") + ` +${who.length - 4}` : who.join(", ")})`);
      if (Object.keys(byPath).length > 60) md.push(`- ... ${Object.keys(byPath).length - 60} more in the JSON file`);
      md.push("");
    }
  };
  group(open, "Open findings");
  if (documented.length) { md.push("", `## Known and documented (${documented.length})`, ""); for (const x of documented.slice(0, 80)) md.push(`- ${x.kind} \`${x.path}\` ${x.role}/${x.mode}: ${x.detail.slice(0, 160)}. Why: ${x.known}`); }
  if (gated.length) {
    md.push("", `## Plan-gated or role-gated responses (${gated.length}, not counted)`, "", "These are 402/403 answers. A 402 means the plan lacks the feature; a 403 means the role is not allowed. Listed so a screen that asks for something its role cannot have is easy to spot.", "");
    const by = {}; for (const x of gated) (by[`${x.path} :: ${x.detail}`] ||= []).push(x.role); for (const [pd, who] of Object.entries(by).slice(0, 80)) md.push(`- \`${pd}\` (${Array.from(new Set(who)).join(", ")})`);
  }
  if (info.length) { md.push("", `## Informational (${info.length})`, ""); const by = {}; for (const x of info) (by[x.kind] ||= new Set()).add(x.role); for (const [k, v] of Object.entries(by)) md.push(`- ${k}: ${Array.from(v).join(", ")} (see JSON for the elements)`); }
  fs.writeFileSync(OUT + ".md", md.join("\n") + "\n");
  console.log(`sweep: ${items.length} records, ${open.length} open, ${documented.length} known, ${gated.length} gated. Report: ${path.relative(ROOT, OUT)}.md`);
  process.exit(open.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
