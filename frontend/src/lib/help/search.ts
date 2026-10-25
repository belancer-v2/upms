import type { Article } from "./types";
import { GROUP_ORDER } from "./types";

/** Lowercase, drop punctuation, keep letters and digits of every script (Bangla included). */
export const norm = (s: string) => s.toLowerCase().normalize("NFC").replace(/[^\p{L}\p{N}\p{M}\s]/gu, " ").replace(/\s+/g, " ").trim();
const words = (s: string) => norm(s).split(" ").filter(Boolean);

/** Edit distance (insert, delete, replace, swap two neighbours) with an early exit; fine for words of a few letters. */
function within(a: string, b: string, max: number): boolean {
  if (Math.abs(a.length - b.length) > max) return false;
  let prev2: number[] = [];
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    let rowMin = i;
    for (let j = 1; j <= b.length; j++) {
      let v = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) v = Math.min(v, prev2[j - 2] + 1);
      cur[j] = v;
      rowMin = Math.min(rowMin, v);
    }
    if (rowMin > max) return false;
    prev2 = prev; prev = cur;
  }
  return prev[b.length] <= max;
}

type Index = { title: string; titleWords: string[]; kw: string; summary: string; body: string; bodyWords: Set<string> };
const cache = new Map<string, Index>();
function index(a: Article): Index {
  let ix = cache.get(a.id);
  if (!ix) {
    const title = norm(`${a.title.en} ${a.title.bn}`);
    const kw = norm(a.keywords ?? "");
    const summary = norm(`${a.summary.en} ${a.summary.bn}`);
    const body = norm([...a.steps.en, ...a.steps.bn, ...a.tips.en, ...a.tips.bn].join(" "));
    ix = { title, titleWords: words(title), kw, summary, body, bodyWords: new Set(words(`${kw} ${summary} ${body}`)) };
    cache.set(a.id, ix);
  }
  return ix;
}

/** One query token against one article. 0 means no match. */
function tokenScore(t: string, ix: Index): number {
  if (ix.title.includes(t)) return 10;
  if (ix.kw.includes(t)) return 6;
  if (ix.summary.includes(t)) return 4;
  if (ix.body.includes(t)) return 2;
  if (t.length >= 4) {   // a typo: one edit for 4 to 7 letters, two for longer
    const max = t.length >= 8 ? 2 : 1;
    if (ix.titleWords.some((w) => within(t, w, max))) return 3;
    for (const w of ix.bodyWords) if (within(t, w, max)) return 1;
  }
  return 0;
}

/** Fuzzy search over title, summary, steps, tips and keywords in both languages. Every word typed must match something. */
export function searchArticles(list: Article[], query: string): Article[] {
  const toks = words(query);
  if (!toks.length) return list;
  return list
    .map((a) => {
      const ix = index(a);
      let total = 0;
      for (const t of toks) {
        const s = tokenScore(t, ix);
        if (!s) return { a, score: 0 };
        total += s;
      }
      return { a, score: total };
    })
    .filter((x) => x.score > 0)
    .sort((x, y) => y.score - x.score || x.a.rank - y.a.rank)
    .map((x) => x.a);
}

/** getting-started first, then guides written for few roles (they are about this person's work), then the general ones. */
const order = (a: Article) => (a.id === "getting-started" ? -1000 : (a.roles.length >= 12 ? 5000 : 0) + GROUP_ORDER.indexOf(a.group) * 100 + a.rank);

/** Articles for the roles the signed-in person holds in this building (plus SaaS role), respecting the building's plan. */
export function recommended(list: Article[], roles: string[], saasRole: string | null | undefined, hasFeature: (k: string) => boolean, max = 6): Article[] {
  const mine = new Set([...roles, ...(saasRole ? [saasRole] : [])]);
  return list
    .filter((a) => a.roles.some((r) => mine.has(r)) && (!a.feature || hasFeature(a.feature) || !!saasRole))
    .sort((x, y) => order(x) - order(y))
    .slice(0, max);
}
