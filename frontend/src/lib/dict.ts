import { core } from "./i18n/core";
import { rolesDict } from "./i18n/roles";
import { feat, site } from "./i18n/site";
import { saasDict } from "./i18n/saas";
import { propertyDict } from "./i18n/property";
import { billingDict } from "./i18n/billing";
import { gatewayDict } from "./i18n/gateway";
import { cashDict } from "./i18n/cash";
import { financeDict } from "./i18n/finance";
import { budgetDict } from "./i18n/budget";
import { staffDict } from "./i18n/staff";
import { noticesDict } from "./i18n/notices";
import { onboardingDict } from "./i18n/onboarding";
import { requestsDict } from "./i18n/requests";
import { profilesDict } from "./i18n/profiles";
import { rentalDict } from "./i18n/rental";
import { amenitiesDict } from "./i18n/amenities";
import { creditsDict } from "./i18n/credits";
import { visitorsDict } from "./i18n/visitors";

import { agencyDict } from "./i18n/agency";

type D = Record<string, string>;
const modules: { en: D; bn: D }[] = [core as unknown as { en: D; bn: D }, rolesDict as unknown as { en: D; bn: D }, site as unknown as { en: D; bn: D }, feat as unknown as { en: D; bn: D }, saasDict as unknown as { en: D; bn: D }, propertyDict as unknown as { en: D; bn: D }, billingDict as unknown as { en: D; bn: D }, gatewayDict as unknown as { en: D; bn: D }, cashDict as unknown as { en: D; bn: D }, financeDict as unknown as { en: D; bn: D }, budgetDict as unknown as { en: D; bn: D }, staffDict as unknown as { en: D; bn: D }, noticesDict as unknown as { en: D; bn: D }, onboardingDict as unknown as { en: D; bn: D }, profilesDict as unknown as { en: D; bn: D }];

modules.push(requestsDict as unknown as { en: D; bn: D });
modules.push(rentalDict as unknown as { en: D; bn: D });
modules.push(amenitiesDict as unknown as { en: D; bn: D });
modules.push(creditsDict as unknown as { en: D; bn: D });
import { parkingDict } from "./i18n/parking";
modules.push(parkingDict as unknown as { en: D; bn: D });

modules.push(agencyDict as unknown as { en: D; bn: D });

modules.push(visitorsDict as unknown as { en: D; bn: D });

export const dict: { en: D; bn: D } = {
  en: Object.assign({}, ...modules.map((m) => m.en)),
  bn: Object.assign({}, ...modules.map((m) => m.bn)),
};
