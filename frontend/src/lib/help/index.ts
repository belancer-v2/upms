import { START } from "./a_start";
import { BUILDING } from "./a_building";
import { MONEY } from "./a_money";
import { PEOPLE } from "./a_people";
import { COMMS } from "./a_comms";
import { LIFE } from "./a_life";
import { REPORTS, DATA, SAAS } from "./a_rest";
import type { Article, HelpGroup, HelpId } from "./types";
import { GROUP_ORDER } from "./types";

export * from "./types";
export const ARTICLES: Article[] = [...START, ...BUILDING, ...MONEY, ...PEOPLE, ...COMMS, ...LIFE, ...REPORTS, ...DATA, ...SAAS];
export const byId = (id: string): Article | undefined => ARTICLES.find((a) => a.id === id);
export const inGroup = (g: HelpGroup, list: Article[] = ARTICLES) => list.filter((a) => a.group === g).sort((a, b) => a.rank - b.rank);
export const groupsOf = (list: Article[]) => GROUP_ORDER.filter((g) => list.some((a) => a.group === g));
export type { Article, HelpGroup, HelpId };
