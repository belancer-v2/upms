import { core } from "./i18n/core";
import { rolesDict } from "./i18n/roles";

type D = Record<string, string>;
const modules: { en: D; bn: D }[] = [core as unknown as { en: D; bn: D }, rolesDict as unknown as { en: D; bn: D }];

export const dict: { en: D; bn: D } = {
  en: Object.assign({}, ...modules.map((m) => m.en)),
  bn: Object.assign({}, ...modules.map((m) => m.bn)),
};
