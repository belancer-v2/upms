import { core } from "./i18n/core";
import { rolesDict } from "./i18n/roles";
import { feat, site } from "./i18n/site";
import { saasDict } from "./i18n/saas";
import { propertyDict } from "./i18n/property";
import { billingDict } from "./i18n/billing";
import { cashDict } from "./i18n/cash";
import { financeDict } from "./i18n/finance";
import { staffDict } from "./i18n/staff";

type D = Record<string, string>;
const modules: { en: D; bn: D }[] = [core as unknown as { en: D; bn: D }, rolesDict as unknown as { en: D; bn: D }, site as unknown as { en: D; bn: D }, feat as unknown as { en: D; bn: D }, saasDict as unknown as { en: D; bn: D }, propertyDict as unknown as { en: D; bn: D }, billingDict as unknown as { en: D; bn: D }, cashDict as unknown as { en: D; bn: D }, financeDict as unknown as { en: D; bn: D }, staffDict as unknown as { en: D; bn: D }];

export const dict: { en: D; bn: D } = {
  en: Object.assign({}, ...modules.map((m) => m.en)),
  bn: Object.assign({}, ...modules.map((m) => m.bn)),
};
