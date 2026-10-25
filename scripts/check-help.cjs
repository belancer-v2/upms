const path = require("path");
// Checks the Help center content: both languages, step parity, images, related ids, role coverage, search, and the i18n keys the P5 screens use.
// Run through scripts/check-help.sh (it compiles the TypeScript first).
const out = process.argv[2];
const { ARTICLES, HELP_IDS } = require(path.join(out, "help/index.js"));
const { searchArticles, recommended } = require(path.join(out, "help/search.js"));
const { dict } = require(path.join(out, "dict.js"));
const fs = require("fs");
let bad = 0; const err = (m) => { bad++; console.log("FAIL", m); };
console.log("articles:", ARTICLES.length, "ids:", HELP_IDS.length);
const ids = new Set(ARTICLES.map((a) => a.id));
for (const id of HELP_IDS) if (!ids.has(id)) err("missing article " + id);
if (ids.size !== ARTICLES.length) err("duplicate ids");
const hasBn = (s) => /[ঀ-৿]/.test(s);
const hasLatinWord = (s) => /[A-Za-z]{4,}/.test(s.replace(/BDT|SMS|CSV|ZIP|OTP|HTTPS|NID|DMP|PSC|TIN|BIN|VAT|bKash|Nagad|Excel|FlatWise|JPG|PNG|PDF|YYYY-MM|English|Google|Sheets|Bangla|Dhaka|SaaS|Sheet/g, ""));
for (const a of ARTICLES) {
  for (const l of ["en", "bn"]) {
    if (!a.title[l] || !a.summary[l]) err(a.id + " empty " + l);
    if (a.steps[l].length < 3) err(a.id + " steps<3 " + l);
    if (a.tips[l].length < 1) err(a.id + " tips " + l);
  }
  if (a.steps.en.length !== a.steps.bn.length) err(a.id + " step count differs EN " + a.steps.en.length + " BN " + a.steps.bn.length);
  if (a.tips.en.length !== a.tips.bn.length) err(a.id + " tip count differs");
  if (hasBn((a.title.en + a.summary.en + a.steps.en.join("") + a.tips.en.join("")).replace(/English or বাংলা|English and বাংলা/g, ""))) err(a.id + " Bangla inside EN text");
  if (!hasBn(a.title.bn + a.summary.bn)) err(a.id + " BN has no Bangla");
  for (const s of a.shots ?? []) { const f = "public" + s.src; if (!fs.existsSync("frontend/" + f)) err(a.id + " missing image " + f); }
  for (const r of a.related ?? []) if (!ids.has(r)) err(a.id + " bad related " + r);
  if (a.route && !a.route.startsWith("/app")) err(a.id + " route");
  for (const r of a.roles) if (!dict.en["role." + r]) err(a.id + " unknown role " + r);
}
// roles coverage: every one of the 17 roles has recommended articles
const ALL = ["AGENCY_MANAGER","PROPERTY_ADMIN","FLAT_OWNER","TENANT","CARETAKER","PRESIDENT","SECRETARY","TREASURER","MEMBER","AUDITOR","GUARD","OWNER_REP","SUPER_ADMIN","SAAS_ADMIN","SAAS_FINANCE","SAAS_SALES","SAAS_USER"];
const all = () => true;
for (const r of ALL) {
  const saas = r.startsWith("S") && ["SUPER_ADMIN","SAAS_ADMIN","SAAS_FINANCE","SAAS_SALES","SAAS_USER"].includes(r) ? r : null;
  const n = ARTICLES.filter((a) => a.roles.includes(r)).length;
  const rec = recommended(ARTICLES, saas ? [] : [r], saas, all);
  console.log(r.padEnd(15), "articles for role:", String(n).padStart(2), " recommended:", rec.map((a) => a.id).slice(0, 3).join(", "));
  if (n < 3) err("role " + r + " has few articles");
}
// search
const q = (s) => searchArticles(ARTICLES, s).slice(0, 3).map((a) => a.id).join(",");
for (const s of ["cash otp", "bkash", "ঈদ বোনাস", "পার্কিং", "reciept", "invoise", "বকেয়া রিমাইন্ডার", "export", "মুছে ফেলা", "xyzzy"]) console.log("search", JSON.stringify(s), "->", q(s) || "(none)");
// i18n keys used in components exist in both languages
const files = require("child_process").execSync("cd frontend && grep -rhoE 't\\(\"(hc|su|dx|s2)\\.[a-zA-Z0-9_.]+\"' src --include=*.tsx --include=*.ts").toString().split("\n").filter(Boolean);
const used = new Set(files.map((x) => x.slice(3, -1)));
for (const k of used) for (const l of ["en", "bn"]) if (!dict[l][k]) err("dict " + l + " missing key " + k);
// dynamic keys
for (const g of ["start","building","money","people","comms","life","reports","data","saas"]) for (const l of ["en","bn"]) if (!dict[l]["hc.group." + g]) err("group " + g);
for (const st of ["building","flats","charges","reminders","committee","review"]) for (const l of ["en","bn"]) { if (!dict[l]["su.s." + st]) err("su.s." + st); }
for (const s of ["done","skipped","known","todo"]) if (!dict.en["su.st." + s] || !dict.bn["su.st." + s]) err("su.st " + s);
for (const k of ["before","dueday","o7","o15","o30"]) if (!dict.en["su.r." + k]) err("su.r." + k);
for (const x of ["service","security","cleaning","lift","generator","water","sinking"]) void x;
for (const k of ["visits","notices","parking_visits","passes","photos"]) if (!dict.en["dx.ret.v." + k]) err("dx.ret.v." + k);
for (const k of ["emails","sms"]) if (!dict.en["dx.ret.o." + k]) err("dx.ret.o." + k);
for (const k of ["contacts","cases","documents"]) if (!dict.en["dx.ret.f." + k]) err("dx.ret.f." + k);
console.log("used keys checked:", used.size, "failures:", bad);
process.exit(bad ? 1 : 0);
