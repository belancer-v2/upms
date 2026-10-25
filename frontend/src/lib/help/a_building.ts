import { art, MGR, RES } from "./types";

const STAFF_VIEW = ["PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "SECRETARY", "TREASURER", "MEMBER", "AUDITOR", "CARETAKER"];

export const BUILDING = [
  art("add-flats", "building", MGR, 1,
    { route: "/app/units", shots: [["add-flats", "Generate flats for every floor and block", "প্রতিটি ফ্লোর ও ব্লকের জন্য ফ্ল্যাট তৈরি"], ["add-flats-parking", "Parking slots created with the flats", "ফ্ল্যাটের সাথে তৈরি পার্কিং স্লট"], ["building-map", "The building map", "ভবনের মানচিত্র"]], related: ["add-people", "parking", "setup-wizard"], keywords: "flats units generate import excel csv floor block area bedrooms ফ্ল্যাট ফ্লোর ইম্পোর্ট" },
    { t: "Adding flats", s: "Create every flat in one go, add one by one, or paste a list from Excel.",
      steps: ["Open Flats and press Add flats.", "On Generate, enter the number of floors, the blocks (for example A,B) and flats per floor per block. Flats are named like A-101, A-102. Set the usual area and bedrooms.", "If your plan includes parking, enter car and motorbike slots per flat. FlatWise creates the slots and gives them to the flats.", "To add a single flat use Add one. To load existing data, open Import and paste rows: number, floor, block, area, bedrooms, owner name, owner phone.", "Check the building map. Colours show occupied, vacant and to-let flats."],
      tips: ["Generating twice is safe: flat numbers that already exist are skipped.", "Importing a number that exists updates it instead of making a duplicate."] },
    { t: "ফ্ল্যাট যোগ করা", s: "একবারে সব ফ্ল্যাট তৈরি করুন, একটি একটি করে যোগ করুন, অথবা এক্সেল থেকে তালিকা পেস্ট করুন।",
      steps: ["ফ্ল্যাট খুলে ফ্ল্যাট যোগ করুন চাপুন।", "তৈরি করুন ট্যাবে ফ্লোর সংখ্যা, ব্লক (যেমন A,B) এবং প্রতি ফ্লোরে প্রতি ব্লকে ফ্ল্যাট সংখ্যা দিন। ফ্ল্যাটের নাম হবে A-101, A-102 এর মতো। সাধারণ আয়তন ও শোবার ঘর দিন।", "প্ল্যানে পার্কিং থাকলে প্রতি ফ্ল্যাটে গাড়ি ও মোটরবাইকের স্লট দিন। ফ্ল্যাটওয়াইজ স্লট তৈরি করে ফ্ল্যাটকে দিয়ে দেয়।", "একটি ফ্ল্যাট যোগ করতে একটি যোগ করুন ব্যবহার করুন। আগের তথ্য আনতে ইম্পোর্ট খুলে সারি পেস্ট করুন: নম্বর, ফ্লোর, ব্লক, আয়তন, শোবার ঘর, মালিকের নাম, মালিকের ফোন।", "ভবনের মানচিত্র দেখুন। রং দিয়ে বসবাসরত, খালি ও ভাড়ার জন্য ফ্ল্যাট বোঝা যায়।"],
      tips: ["দুইবার তৈরি করলেও ক্ষতি নেই: যে ফ্ল্যাট নম্বর আছে তা বাদ যায়।", "বিদ্যমান নম্বর ইম্পোর্ট করলে নকল না হয়ে হালনাগাদ হয়।"] }),

  art("add-people", "building", MGR, 2,
    { route: "/app/units", shots: [["flat-detail", "A flat with its owner and tenant", "মালিক ও ভাড়াটিয়াসহ একটি ফ্ল্যাট"], ["people", "The people list", "মানুষের তালিকা"]], related: ["add-flats", "tenant-onboarding", "move-out-data"], keywords: "owner tenant add person login sign-in temporary password move out মালিক ভাড়াটিয়া লগইন" },
    { t: "Adding owners and tenants", s: "Record who owns and who lives in each flat, and give them a sign-in if they should use FlatWise.",
      steps: ["Open Flats and tap a flat on the map or in the list.", "Press Add person. Choose Owner or Tenant, then enter the full name, phone and email.", "For an owner, tick Owner lives in this flat if that is true. A flat has one tenant at a time.", "Tick Create a sign-in for this person (needs an email). FlatWise shows a temporary password once. Give it to the person and ask them to change it.", "When someone leaves, open the flat and press Move out. The record stays in History and their sign-in for this building stops."],
      tips: ["Owners can add their own tenant from My flat, without waiting for the admin.", "People who only need to be on record, such as an owner who lives abroad, do not need a sign-in."] },
    { t: "মালিক ও ভাড়াটিয়া যোগ করা", s: "প্রতিটি ফ্ল্যাটের মালিক ও বাসিন্দা লিখে রাখুন এবং ফ্ল্যাটওয়াইজ ব্যবহার করতে হলে সাইন ইন দিন।",
      steps: ["ফ্ল্যাট খুলে মানচিত্র বা তালিকা থেকে একটি ফ্ল্যাটে চাপুন।", "ব্যক্তি যোগ করুন চাপুন। মালিক বা ভাড়াটিয়া বেছে পুরো নাম, ফোন ও ইমেইল দিন।", "মালিক হলে এবং তিনি সেখানে থাকলে মালিক এই ফ্ল্যাটে থাকেন টিক দিন। একটি ফ্ল্যাটে একসময়ে একজন ভাড়াটিয়া থাকেন।", "এই ব্যক্তির জন্য সাইন ইন তৈরি করুন (ইমেইল লাগবে) টিক দিন। ফ্ল্যাটওয়াইজ অস্থায়ী পাসওয়ার্ড একবার দেখায়। ব্যক্তিকে দিয়ে বদলে নিতে বলুন।", "কেউ চলে গেলে ফ্ল্যাট খুলে চলে গেছেন চাপুন। রেকর্ড ইতিহাসে থাকে এবং এই ভবনে তাঁর সাইন ইন বন্ধ হয়।"],
      tips: ["মালিক নিজেই আমার ফ্ল্যাট থেকে ভাড়াটিয়া যোগ করতে পারেন, অ্যাডমিনের জন্য অপেক্ষা না করে।", "যাঁকে শুধু রেকর্ডে রাখা দরকার, যেমন প্রবাসী মালিক, তাঁর সাইন ইন লাগে না।"] }),

  art("building-details", "building", MGR, 3,
    { route: "/app/building", shots: [["building-map", "Flats map with status colours", "অবস্থার রংসহ ফ্ল্যাট মানচিত্র"]], related: ["setup-wizard", "add-flats"], keywords: "building settings name address bangla name to let offer approve ভবন ঠিকানা ভাড়া" },
    { t: "Building details and letting a flat", s: "Keep the name and address right, because they print on every bill, notice and receipt. Offer vacant flats to let with the owner's approval.",
      steps: ["Open Building settings from the menu.", "Enter the building name in English and in Bangla, the address and the number of floors, then save.", "To offer a vacant flat, open it on the Flats screen and press Offer to let. The flat shows Waiting for owner.", "The owner opens My flat or the flat and presses Approve letting. Only then is the flat shown as To let.", "Either side can withdraw the offer."],
      tips: ["Fill the Bangla name so Bangla bills and SMS show the right building name.", "Tenant onboarding needs a flat that is To let."] },
    { t: "ভবনের তথ্য ও ফ্ল্যাট ভাড়া দেওয়া", s: "নাম ও ঠিকানা ঠিক রাখুন, কারণ এগুলো প্রতিটি বিল, নোটিশ ও রসিদে ছাপা হয়। খালি ফ্ল্যাট মালিকের অনুমতি নিয়ে ভাড়ার জন্য দিন।",
      steps: ["মেনু থেকে ভবনের সেটিংস খুলুন।", "ইংরেজি ও বাংলায় ভবনের নাম, ঠিকানা ও ফ্লোর সংখ্যা দিয়ে সংরক্ষণ করুন।", "খালি ফ্ল্যাট ভাড়ার জন্য দিতে ফ্ল্যাট পর্দায় ফ্ল্যাট খুলে ভাড়ার জন্য দিন চাপুন। ফ্ল্যাট মালিকের অপেক্ষায় দেখাবে।", "মালিক আমার ফ্ল্যাট বা ফ্ল্যাট খুলে ভাড়ায় সম্মতি চাপেন। তখনই ফ্ল্যাট ভাড়ার জন্য দেখায়।", "যেকোনো পক্ষ প্রস্তাব ফিরিয়ে নিতে পারে।"],
      tips: ["বাংলা নাম দিন, তাহলে বাংলা বিল ও এসএমএসে সঠিক ভবনের নাম আসবে।", "ভাড়াটিয়া অনবোর্ডিংয়ের জন্য ফ্ল্যাট ভাড়ার জন্য থাকতে হবে।"] }),

  art("agency-portfolio", "building", ["AGENCY_MANAGER"], 4,
    { route: "/app/portfolio", shots: [["portfolio", "Every building you manage", "আপনার পরিচালিত সব ভবন"]], related: ["building-details", "building-reports"], keywords: "agency manager portfolio many buildings compare এজেন্সি পোর্টফোলিও" },
    { t: "Managing many buildings as an agency", s: "One sign-in for all the buildings your agency runs, with occupancy side by side.",
      steps: ["Open Portfolio. Each card is one building with flats and how full it is.", "Press Add a building, enter name, address, city and floors, and save.", "Press Open building to work inside one. The building box at the top switches between buildings at any time.", "Everything you do inside a building is kept separate from the other buildings."],
      tips: ["An agency manager's role covers every building of the agency, including ones added later.", "Each building has its own plan, charges, committee and data."] },
    { t: "এজেন্সি হিসেবে একাধিক ভবন পরিচালনা", s: "আপনার এজেন্সির সব ভবনের জন্য একটি সাইন ইন, পাশাপাশি বসবাসের হার দেখে।",
      steps: ["পোর্টফোলিও খুলুন। প্রতিটি কার্ড একটি ভবন, ফ্ল্যাট সংখ্যা ও কতটা ভরা তাসহ।", "ভবন যোগ করুন চাপুন, নাম, ঠিকানা, শহর ও ফ্লোর দিয়ে সংরক্ষণ করুন।", "একটির ভেতরে কাজ করতে ভবন খুলুন চাপুন। ওপরের ভবন বাক্স দিয়ে যেকোনো সময় ভবন বদলানো যায়।", "এক ভবনে যা করবেন তা অন্য ভবন থেকে আলাদা থাকে।"],
      tips: ["এজেন্সি ম্যানেজারের ভূমিকা এজেন্সির সব ভবনে খাটে, পরে যোগ করা ভবনেও।", "প্রতিটি ভবনের নিজস্ব প্ল্যান, চার্জ, কমিটি ও তথ্য আছে।"] }),

  art("my-flat", "building", RES, 5,
    { route: "/app/my-flat", shots: [["my-flat", "My flat for an owner", "মালিকের জন্য আমার ফ্ল্যাট"]], related: ["pay-service-charge", "rental-records", "hall-booking"], keywords: "owner tenant my flat add my tenant approve letting আমার ফ্ল্যাট" },
    { t: "My flat", s: "See your flat, the people in it and the things only you can do as the owner.",
      steps: ["Open My flat from the menu.", "You see your flat number, floor, area, the owners and the tenant.", "As an owner, press Add my tenant to record a new tenant, then follow the tenant onboarding steps.", "If the admin offered your vacant flat to let, press Approve letting to agree.", "If the screen says no flat is linked to your sign-in, ask the building admin to link it."],
      tips: ["Your bills are on My dues and your parking on Parking.", "Tenants see the flat but cannot change owners or letting."] },
    { t: "আমার ফ্ল্যাট", s: "আপনার ফ্ল্যাট, তার মানুষজন এবং মালিক হিসেবে যা শুধু আপনি করতে পারেন তা দেখুন।",
      steps: ["মেনু থেকে আমার ফ্ল্যাট খুলুন।", "ফ্ল্যাটের নম্বর, ফ্লোর, আয়তন, মালিক ও ভাড়াটিয়া দেখতে পাবেন।", "মালিক হলে আমার ভাড়াটিয়া যোগ করুন চেপে নতুন ভাড়াটিয়া লিখুন, তারপর ভাড়াটিয়া অনবোর্ডিংয়ের ধাপ অনুসরণ করুন।", "অ্যাডমিন আপনার খালি ফ্ল্যাট ভাড়ার জন্য দিলে ভাড়ায় সম্মতি চেপে রাজি হন।", "পর্দায় সাইন ইনের সাথে কোনো ফ্ল্যাট যুক্ত নেই লেখা থাকলে ভবনের অ্যাডমিনকে যুক্ত করতে বলুন।"],
      tips: ["বিল দেখবেন আমার বকেয়ায় আর পার্কিং দেখবেন পার্কিংয়ে।", "ভাড়াটিয়া ফ্ল্যাট দেখতে পান, কিন্তু মালিক বা ভাড়ার সিদ্ধান্ত বদলাতে পারেন না।"] }),
];
export default BUILDING;
