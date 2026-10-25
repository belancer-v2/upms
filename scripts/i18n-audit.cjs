#!/usr/bin/env node
// Usage: node scripts/i18n-audit.cjs [--json] [--quiet]     (npm run i18n:audit from frontend/ or the repo root)
// Checks the BN/EN dictionaries in frontend/src/lib/i18n and how the code uses them. Exit code 1 when anything is wrong.
//   1. dictionary files that dict.ts does not load
//   2. keys missing in en or bn, empty values
//   3. keys used in code (t("a.b")) that exist in neither language; dynamic keys t(`a.${x}`) that match nothing
//   4. {placeholder} mismatches between en and bn
//   5. hard-coded English in JSX text and in title/placeholder/aria-label/alt/label attributes, confirm/alert/prompt/toast strings
//   6. number and date formatting that is not Latin digits / en-GB (money must read "BDT 1,200", dates en-GB)
//   7. the same key defined in two dictionary files (the later one silently wins)
const fs = require("fs");
const path = require("path");
const Module = require("module");
const ROOT = path.join(__dirname, "..");
const FE = path.join(ROOT, "frontend");
const SRC = path.join(FE, "src");
const ts = require(path.join(FE, "node_modules", "typescript"));
const args = new Set(process.argv.slice(2));

// ---------------------------------------------------------------- load .ts dictionaries without a build step
require.extensions[".ts"] = function (module, filename) {
  const out = ts.transpileModule(fs.readFileSync(filename, "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true }, fileName: filename });
  module._compile(out.outputText, filename);
};
const I18N = path.join(SRC, "lib", "i18n");
const files = fs.readdirSync(I18N).filter((f) => f.endsWith(".ts")).sort();
const defs = {}; // key -> [{file, en, bn}]
const perFile = {};
for (const f of files) {
  const mod = require(path.join(I18N, f));
  for (const [name, val] of Object.entries(mod)) {
    if (val && typeof val === "object" && val.en && val.bn && typeof val.en === "object") {
      perFile[`${f}:${name}`] = val;
    }
  }
}
const ALLOWED_LATIN_IN_BN = new Set(["flatwise", "upms", "email", "bkash", "nagad", "dbbl", "rocket", "visa", "mastercard", "sandbox", "https", "http", "www", "demo", "desco", "wasa", "dhaka", "metro", "nid", "otp", "sms", "pdf", "csv", "jpg", "png", "bdt", "vat", "bin", "tin", "psc", "cctv", "amc", "mrr", "sqft", "kvah", "yyyy", "iban", "swift", "uptime", "api", "html", "unsubscribe"]);
const problems = []; // {kind, where, msg}
const add = (kind, where, msg) => problems.push({ kind, where, msg });
const rel = (p) => path.relative(ROOT, p);

// 1. every dictionary must be loaded by dict.ts
const dictSrc = fs.readFileSync(path.join(SRC, "lib", "dict.ts"), "utf8");
for (const id of Object.keys(perFile)) {
  const [f, name] = id.split(":");
  if (!new RegExp(`\\b${name}\\b`).test(dictSrc)) add("dict-not-loaded", `frontend/src/lib/i18n/${f}`, `export "${name}" is not imported in lib/dict.ts, so its keys never reach the screen`);
}

const en = {}, bn = {};
for (const [id, val] of Object.entries(perFile)) {
  const f = id.split(":")[0];
  for (const lang of ["en", "bn"]) {
    for (const [k, v] of Object.entries(val[lang])) {
      (lang === "en" ? en : bn)[k] = v;
      (defs[`${lang}:${k}`] ||= []).push({ file: f, v });
    }
  }
}
// 7. duplicates
for (const [id, list] of Object.entries(defs)) {
  if (list.length > 1) {
    const vals = new Set(list.map((x) => x.v));
    if (vals.size > 1) add("duplicate-key", id, `defined in ${list.map((x) => x.file).join(", ")} with different text (the last file loaded wins)`);
  }
}
// 2. missing / empty
const keys = new Set([...Object.keys(en), ...Object.keys(bn)]);
for (const k of keys) {
  if (!(k in en)) add("missing-en", k, "present in bn, missing in en");
  else if (!(k in bn)) add("missing-bn", k, "present in en, missing in bn");
  else {
    if (!String(en[k]).trim()) add("empty", k, "empty en text");
    if (!String(bn[k]).trim()) add("empty", k, "empty bn text");
  }
}
// 4. placeholders
const ph = (s) => Array.from(new Set((String(s).match(/\{[a-zA-Z_][a-zA-Z0-9_]*\}/g) || []))).sort().join(",");
for (const k of keys) if (k in en && k in bn && ph(en[k]) !== ph(bn[k])) add("placeholder", k, `en uses [${ph(en[k])}] but bn uses [${ph(bn[k])}]`);
// Bangla text in the English dictionary and English prose in the Bangla one
const BN_RE = /[ঀ-৿]/;
// Language names are written in their own script on purpose, and a few help strings name the CSV columns literally.
const MIX_OK = /(^|\.)lang(_en|_bn)?(\.|$)|^set\.lang\.|^hc\.search$|^mail\.csv\.help$/;
for (const k of keys) {
  if (MIX_OK.test(k)) continue;
  if (k in en && BN_RE.test(en[k])) add("script-mix", k, "Bangla letters inside the English text");
  if (k in bn) {
    const words = String(bn[k]).replace(/\{[^}]*\}/g, "").match(/[A-Za-z]{4,}/g) || [];
    const stray = words.filter((w) => !ALLOWED_LATIN_IN_BN.has(w.toLowerCase()));
    if (stray.length) add("script-mix", k, `English words inside the Bangla text: ${stray.slice(0, 4).join(", ")}`);
  }
}

// ---------------------------------------------------------------- code scan
function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) { if (e.name !== "node_modules" && !e.name.startsWith(".")) walk(p, out); }
    else if (/\.(tsx?|mts)$/.test(e.name) && !e.name.endsWith(".d.ts")) out.push(p);
  }
  return out;
}
const codeFiles = walk(SRC).filter((p) => !p.startsWith(I18N + path.sep));
const used = new Map(); // key -> first location
const dynamic = []; // {regex, where, src}
const hard = [];
const keyShape = /^[a-z][a-z0-9]*(\.[a-zA-Z0-9_\-]+)+$/;
const namespaces = new Set(Array.from(keys).map((k) => k.split(".")[0]));

const OK_TEXT = new Set(["bdt", "sms", "otp", "nid", "pdf", "csv", "flatwise", "upms", "bkash", "nagad", "en", "bn", "am", "pm", "ok", "id", "vat", "tin", "bin", "tk", "kb", "mb", "jpg", "png", "n/a", "cctv", "amc", "dmp", "ui", "qr", "url", "sq", "ft", "sqft", "kva", "gb", "db", "arr", "mrr", "english", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]);
const hasWords = (s) => /[A-Za-z]{2,}/.test(s);
const englishy = (s) => {
  const t = s.replace(/\s+/g, " ").trim();
  if (!hasWords(t)) return false;
  if (/https?:\/\/|@example\.|^[.#][\w-]+\s*\{/.test(t) || /^[\w@. -]+(,\s?[\w@. -]+){3,}/.test(t)) return false;   // URLs, CSS, sample CSV rows
  const words = t.match(/[A-Za-z]{2,}/g) || [];
  return !words.every((w) => OK_TEXT.has(w.toLowerCase()));
};

function checkFile(p) {
  const text = fs.readFileSync(p, "utf8");
  const sf = ts.createSourceFile(p, text, ts.ScriptTarget.ES2022, true, p.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const isUi = /[\\/]src[\\/](app|components)[\\/]/.test(p);
  const lines = text.split("\n");
  const where = (n) => `${rel(p)}:${sf.getLineAndCharacterOfPosition(n.getStart()).line + 1}`;
  const okLine = (n) => /i18n-ok/.test(lines[sf.getLineAndCharacterOfPosition(n.getStart()).line] || "");
  const inHidden = (n) => { for (let a = n.parent; a; a = a.parent) if (ts.isJsxElement(a) && a.openingElement.attributes.properties.some((pr) => ts.isJsxAttribute(pr) && pr.name.getText() === "aria-hidden")) return true; return false; };
  const inStyleTag = (n) => { for (let a = n.parent; a; a = a.parent) if (ts.isJsxElement(a)) return a.openingElement.tagName.getText() === "style"; return false; };
  const hardAdd = (n, h) => { if (!okLine(n) && !inStyleTag(n) && !inHidden(n)) hard.push({ where: where(n), ...h }); };
  const visit = (n) => {
    // t("key") / t(`key.${x}`)
    if (ts.isCallExpression(n) && ts.isIdentifier(n.expression) && (n.expression.text === "t" || n.expression.text === "tr") && n.arguments.length) {
      const a = n.arguments[0];
      if (ts.isStringLiteral(a) || ts.isNoSubstitutionTemplateLiteral(a)) { if (!used.has(a.text)) used.set(a.text, where(n)); }
      else if (ts.isTemplateExpression(a)) {
        const re = "^" + [a.head.text, ...a.templateSpans.map((s) => s.literal.text)].map((x) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join(".+") + "$";
        dynamic.push({ re: new RegExp(re), where: where(n), src: a.getText() });
      }
    }
    // string literals that look like dictionary keys of a known namespace (nav.ts "nav.home", ROLE tables ...)
    if ((ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) && keyShape.test(n.text) && namespaces.has(n.text.split(".")[0]) && !used.has(n.text) && !/^(next|react)/.test(n.text) && !Array.from(keys).some((k) => k.startsWith(n.text + "."))) {   // a bare namespace such as "plan.name" is a prefix, not a key
      const par = n.parent;
      const isImport = par && (ts.isImportDeclaration(par) || ts.isExportDeclaration(par) || ts.isImportTypeNode(par));
      if (!isImport && !/\.(tsx?|json|css|png|jpe?g|svg|pdf|zip|csv)$/.test(n.text) && !/^(window|document|localStorage|console|Math|JSON|Intl)\./.test(n.text)) used.set(n.text, "~" + where(n));
    }
    if (isUi) {
      if (ts.isJsxText(n)) {
        const s = n.getText().replace(/\s+/g, " ").trim();
        if (s && englishy(s)) hardAdd(n, { kind: "jsx-text", text: s });
      }
      if (ts.isJsxAttribute(n) && n.initializer && ts.isStringLiteral(n.initializer) && /^(title|placeholder|aria-label|alt|label|aria-description|hint|sub|eyebrow|note|head|text|description|tooltip)$/.test(n.name.getText())) {
        if (englishy(n.initializer.text)) hardAdd(n, { kind: `attr ${n.name.getText()}`, text: n.initializer.text });
      }
      // {cond ? "English" : "English"} and {x && "English"} inside JSX children or text-like attributes
      if (ts.isJsxExpression(n) && n.expression) {
        const textAttr = ts.isJsxAttribute(n.parent) ? /^(title|placeholder|aria-label|alt|label|aria-description|hint|sub|eyebrow|note|head|text|description|tooltip)$/.test(n.parent.name.getText()) : true;
        const lits = [];
        const grab = (e) => {
          if (!e) return;
          if (ts.isStringLiteral(e) || ts.isNoSubstitutionTemplateLiteral(e)) lits.push(e);
          else if (ts.isParenthesizedExpression(e)) grab(e.expression);
          else if (ts.isConditionalExpression(e)) {
            // {bn ? "বাংলা" : "English"} is a deliberate two-language pair (pages that render without the dictionary, such as global-error)
            const isStr = (x) => ts.isStringLiteral(x) || ts.isNoSubstitutionTemplateLiteral(x);
            if (isStr(e.whenTrue) && isStr(e.whenFalse) && (/[\u0980-\u09FF]/.test(e.whenTrue.text) || /[\u0980-\u09FF]/.test(e.whenFalse.text))) return;
            grab(e.whenTrue); grab(e.whenFalse);
          }
          else if (ts.isBinaryExpression(e) && [ts.SyntaxKind.AmpersandAmpersandToken, ts.SyntaxKind.BarBarToken, ts.SyntaxKind.QuestionQuestionToken].includes(e.operatorToken.kind)) grab(e.right);
        };
        if (textAttr) grab(n.expression);
        for (const l of lits) if (englishy(l.text)) hardAdd(l, { kind: "jsx-expr", text: l.text });
      }
      if (ts.isCallExpression(n)) {
        const callee = n.expression.getText();
        if (/^(window\.)?(confirm|alert|prompt)$/.test(callee) || /(^|\.)toast(\.show)?$/.test(callee) || /^setErr$/.test(callee) || /^show$/.test(callee)) {
          const a = n.arguments[0];
          if (a && (ts.isStringLiteral(a) || ts.isNoSubstitutionTemplateLiteral(a)) && englishy(a.text)) hardAdd(n, { kind: callee, text: a.text });
        }
      }
      if (ts.isNewExpression(n) && n.expression.getText() === "Error" && n.arguments && n.arguments[0] && (ts.isStringLiteral(n.arguments[0]) || ts.isNoSubstitutionTemplateLiteral(n.arguments[0])) && englishy(n.arguments[0].text)) {
        hardAdd(n, { kind: "new Error", text: n.arguments[0].text });
      }
    }
    // number and date formatting
    if (ts.isCallExpression(n) && ts.isPropertyAccessExpression(n.expression) && /^toLocale(Date|Time)?String$/.test(n.expression.name.text)) {
      const a = n.arguments[0];
      const ok = a && ts.isStringLiteral(a) && /^en-(GB|US)$/.test(a.text);
      if (!ok) add("locale", where(n), `${n.expression.name.text}() must be called with "en-GB" (dates) or "en-US" (numbers) so digits stay Latin`);
    }
    if (ts.isNewExpression(n) && /^Intl\.(NumberFormat|DateTimeFormat)$/.test(n.expression.getText())) {
      const a = n.arguments && n.arguments[0];
      if (!(a && ts.isStringLiteral(a) && /^en-(GB|US)$/.test(a.text))) add("locale", where(n), `${n.expression.getText()} needs an explicit en-GB / en-US locale`);
    }
    ts.forEachChild(n, visit);
  };
  visit(sf);
  if (/[৳]|\bTk\.?\s?\d|\bTaka\b/.test(text) && !p.startsWith(I18N)) add("money-format", rel(p), "money must be written as BDT with Latin digits (found ৳ / Tk / Taka)");
}
for (const p of codeFiles) checkFile(p);

// 3b. values the backend stores that the screens turn into words through a dynamic key: plan features, SMS template names, roles
const BE = path.join(ROOT, "backend", "app");
const read = (f) => { try { return fs.readFileSync(path.join(BE, f), "utf8"); } catch { return ""; } };
const need = (prefix, names, from) => { for (const n of names) if (!(`${prefix}.${n}` in en) || !(`${prefix}.${n}` in bn)) add("missing-key", `${prefix}.${n}`, `the backend defines "${n}" (${from}) but the dictionary has no text for it`); };
{
  const feats = (read("services/entitlements.py").match(/ALL_FEATURES\s*=\s*\[([^\]]*)\]/) || [])[1];
  if (feats) need("feat", feats.match(/"([a-z_]+)"/g).map((x) => x.replace(/"/g, "")), "services/entitlements.py ALL_FEATURES");
  const tpls = new Set();
  const walkPy = (d) => { for (const e of fs.readdirSync(d, { withFileTypes: true })) { const q = path.join(d, e.name); if (e.isDirectory()) { if (e.name !== "__pycache__") walkPy(q); } else if (e.name.endsWith(".py")) { const src = fs.readFileSync(q, "utf8"); for (const m of src.matchAll(/template="([a-z_]+)"/g)) tpls.add(m[1]); for (const m of src.matchAll(/_notify\([^\n]*?, "(booking_[a-z]+)"/g)) tpls.add(m[1]); } } };
  walkPy(BE);
  const steps = (read("routers/billing.py").match(/^STEPS\s*=\s*\[(.*)\]/m) || [])[1];
  if (steps) for (const m of steps.matchAll(/\("([a-z0-9]+)"/g)) tpls.add(`due_${m[1]}`);
  need("msg.tpl", Array.from(tpls), "Message.template");
  const roles = (read("models/core.py").match(/SAAS_ROLES\s*=\s*\[([^\]]*)\]/) || [])[1];
  if (roles) need("role", roles.match(/"([A-Z_]+)"/g).map((x) => x.replace(/"/g, "")), "models/core.py SAAS_ROLES");
}

// 3. used but undefined
for (const [k, w] of used) if (!(k in en) && !(k in bn)) add(w.startsWith("~") ? "unknown-key?" : "missing-key", k, `used at ${w.replace(/^~/, "")}`);
for (const k of used.keys()) {
  if ((k in en) !== (k in bn) && (k in en || k in bn)) { /* already reported as missing-en/bn */ }
}
for (const d of dynamic) if (!Array.from(keys).some((k) => d.re.test(k))) add("missing-key", d.src, `dynamic key at ${d.where} matches no dictionary key`);
for (const h of hard) add("hardcoded-english", h.where, `${h.kind}: "${h.text.slice(0, 90)}"`);

// unused (information only)
const dynRes = dynamic.map((d) => d.re);
const unused = Array.from(keys).filter((k) => !used.has(k) && !dynRes.some((re) => re.test(k)));

// money in dictionaries: BN text must not use the taka sign or Bangla word for BDT next to digits
for (const k of Object.keys(bn)) {
  if (/(৳|টাকা)\s*[0-9০-৯]|[0-9০-৯][0-9০-৯,.]*\s*(৳|টাকা)/.test(bn[k]) || /BDT\s*[০-৯]/.test(bn[k])) add("money-format", k, "Bangla text writes an amount with ৳/টাকা or Bangla digits; use BDT with Latin digits");
}

// ---------------------------------------------------------------- report
const byKind = {};
for (const p of problems) (byKind[p.kind] ||= []).push(p);
if (args.has("--json")) { console.log(JSON.stringify({ keys: keys.size, problems, unused: unused.length }, null, 1)); process.exit(problems.length ? 1 : 0); }
console.log(`i18n audit: ${keys.size} keys (${Object.keys(en).length} en, ${Object.keys(bn).length} bn) in ${files.length} dictionary files; ${codeFiles.length} code files scanned; ${used.size} static keys used`);
for (const [kind, list] of Object.entries(byKind)) {
  console.log(`\n${kind}: ${list.length}`);
  if (!args.has("--quiet")) for (const p of list.slice(0, 400)) console.log(`  ${p.where}  ${p.msg}`);
}
if (!args.has("--quiet") && unused.length) console.log(`\n(info) ${unused.length} dictionary keys are not referenced by a literal t() call (dynamic use is possible)`);
console.log(problems.length ? `\nFAILED: ${problems.length} problem(s)` : "\nOK: no problems");
process.exit(problems.length ? 1 : 0);
