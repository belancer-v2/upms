import { core } from "./i18n/core";
import { rolesDict } from "./i18n/roles";
import { feat, site } from "./i18n/site";
import { saasDict } from "./i18n/saas";
import { saasReportsDict } from "./i18n/saasreports";
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
import { mailDict } from "./i18n/mail";
import { amenitiesDict } from "./i18n/amenities";
import { creditsDict } from "./i18n/credits";
import { visitorsDict } from "./i18n/visitors";

import { agencyDict } from "./i18n/agency";

type D = Record<string, string>;
const modules: { en: D; bn: D }[] = [core as unknown as { en: D; bn: D }, rolesDict as unknown as { en: D; bn: D }, site as unknown as { en: D; bn: D }, feat as unknown as { en: D; bn: D }, saasDict as unknown as { en: D; bn: D }, propertyDict as unknown as { en: D; bn: D }, billingDict as unknown as { en: D; bn: D }, gatewayDict as unknown as { en: D; bn: D }, cashDict as unknown as { en: D; bn: D }, financeDict as unknown as { en: D; bn: D }, budgetDict as unknown as { en: D; bn: D }, staffDict as unknown as { en: D; bn: D }, noticesDict as unknown as { en: D; bn: D }, onboardingDict as unknown as { en: D; bn: D }, profilesDict as unknown as { en: D; bn: D }];

modules.push(requestsDict as unknown as { en: D; bn: D });
modules.push(saasReportsDict as unknown as { en: D; bn: D });
modules.push(rentalDict as unknown as { en: D; bn: D });
modules.push(mailDict as unknown as { en: D; bn: D });
modules.push(amenitiesDict as unknown as { en: D; bn: D });
modules.push(creditsDict as unknown as { en: D; bn: D });
import { parkingDict } from "./i18n/parking";
modules.push(parkingDict as unknown as { en: D; bn: D });

modules.push(agencyDict as unknown as { en: D; bn: D });

modules.push(visitorsDict as unknown as { en: D; bn: D });

import { p4Dict } from "./i18n/p4";
modules.push(p4Dict as unknown as { en: D; bn: D });
import { actDict } from "./i18n/act";
modules.push(actDict as unknown as { en: D; bn: D });

import { jobsDict } from "./i18n/jobs";
modules.push(jobsDict as unknown as { en: D; bn: D });

// P5: help center, setup wizard, data export and retention, public site pages
import { helpDict } from "./i18n/help";
import { setupDict } from "./i18n/setup";
import { datatoolsDict } from "./i18n/datatools";
import { site2Dict } from "./i18n/site2";
modules.push(helpDict as unknown as { en: D; bn: D }, setupDict as unknown as { en: D; bn: D }, datatoolsDict as unknown as { en: D; bn: D }, site2Dict as unknown as { en: D; bn: D });

import { authxDict } from "./i18n/authx";
modules.push(authxDict as unknown as { en: D; bn: D });

export const dict: { en: D; bn: D } = {
  en: Object.assign({}, ...modules.map((m) => m.en)),
  bn: Object.assign({}, ...modules.map((m) => m.bn)),
};
