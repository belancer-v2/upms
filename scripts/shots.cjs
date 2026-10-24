// Usage: node scripts/shots.cjs scripts/shots/m0.json
// Logs in as each demo role, opens the page, saves docs/screenshots/<module>/<name>.png
const fs = require("fs"); const path = require("path");
const { chromium } = require("playwright");
const BASE = process.env.WEB || "http://127.0.0.1:3000";
(async () => {
  const cfg = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  const out = path.join(__dirname, "..", "docs", "screenshots", cfg.module); fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch();
  for (const s of cfg.shots) {
    const w = s.w || 1440, h = s.h || 900;
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    let token = "", propId = 0;
    if (s.as) {
      const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: `${s.as}@flatwise.demo`, password: "demo1234" }) });
      const d = await r.json(); token = d.token;
      const p = d.properties.find((x) => !s.prop || x.name === s.prop) || d.properties[0]; propId = p ? p.id : 0;
    }
    await ctx.addInitScript(([t, p, l, th]) => { try { if (t) localStorage.setItem("fw_token", t); if (p) localStorage.setItem("fw_prop", String(p)); localStorage.setItem("fw_lang", l); localStorage.setItem("fw_theme", th); } catch (e) {} }, [token, propId, s.lang || "en", s.theme || "light"]);
    const page = await ctx.newPage();
    await page.goto(BASE + s.path, { waitUntil: "networkidle" });
    if (s.click) { for (const c of [].concat(s.click)) { await page.click(c); await page.waitForTimeout(400); } }
    await page.waitForTimeout(s.wait || 700);
    await page.screenshot({ path: path.join(out, s.name + ".png"), fullPage: !!s.full });
    await ctx.close(); console.log("shot", cfg.module, s.name);
  }
  await browser.close();
})();
