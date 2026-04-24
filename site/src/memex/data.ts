export type Source = "screen" | "email" | "calendar" | "notif" | "filesys";

export interface RawEvent {
  id: string;
  source: Source;
  ts: string;
  text: string;
}

export interface Label {
  id: string;
  rawId: string;
  text: string;
  pages: string[];
}

export type WikiBlock =
  | { kind: "p"; text: string }
  | { kind: "h"; text: string }
  | { kind: "updated"; date: string; text: string }
  | { kind: "unknown"; items: string[] };

export interface WikiPage {
  slug: string;
  dir: "people" | "projects" | "interests" | "work";
  title: string;
  confidenceStart: number;
  confidenceEnd: number;
  lastUpdated: string;
  lede: string;
  body: WikiBlock[];
}

export interface GraphNode {
  slug: string;
  label: string;
  x: number;
  y: number;
  r: number;
}

export interface GraphEdge {
  from: string;
  to: string;
}

export const RAW_EVENTS: RawEvent[] = [
  { id: "r01", source: "screen", ts: "08:14:02", text: "opened farmhouse_journal.md" },
  { id: "r02", source: "filesys", ts: "08:14:31", text: "~/journal/2026-04-23.md — wrote 412 words" },
  { id: "r03", source: "screen", ts: "08:16:10", text: "viewed photos/toto_aug.jpg, photos/toto_oct.jpg" },
  { id: "r04", source: "email",   ts: "08:22:48", text: "from: zeke@kansasprairie.farm — 'storm coming in tomorrow, batten the cellar'" },
  { id: "r05", source: "calendar",ts: "08:23:14", text: "event: Aunt Em — birthday (Nov 30, annual)" },
  { id: "r06", source: "notif",   ts: "08:24:01", text: "Weather — Tornado Watch, Cowley County, KS" },
  { id: "r07", source: "screen",  ts: "08:27:55", text: "read wikipedia: yellow brick road" },
  { id: "r08", source: "filesys", ts: "08:31:02", text: "~/sketches/scarecrow_pose_01.png — created" },
  { id: "r09", source: "email",   ts: "08:34:20", text: "from: glinda@emeraldcity.oz — 'slippers confirmed, ruby'" },
  { id: "r10", source: "screen",  ts: "08:37:18", text: "read wikipedia: tin woodman" },
  { id: "r11", source: "calendar",ts: "08:38:40", text: "event: meet Scarecrow — Mile 4, Yellow Brick Road" },
  { id: "r12", source: "notif",   ts: "08:41:09", text: "Signal — Tin Man: 'brought my oil can'" },
  { id: "r13", source: "screen",  ts: "08:43:33", text: "opened notes/oz_plan.md — 'get to Emerald City'" },
  { id: "r14", source: "filesys", ts: "08:45:12", text: "~/journal/2026-04-23.md — appended 188 words" },
  { id: "r15", source: "email",   ts: "08:47:55", text: "from: aunt.em@auntiekansas.net — 'the dog is fine, come home when you can'" },
  { id: "r16", source: "screen",  ts: "08:49:20", text: "viewed map: oz_overworld.png (zoom 3x)" },
  { id: "r17", source: "notif",   ts: "08:51:44", text: "Signal — Cowardly Lion: 'i'm coming'" },
  { id: "r18", source: "calendar",ts: "08:54:00", text: "event: audience with the Wizard — Thurs 2pm" },
  { id: "r19", source: "screen",  ts: "08:56:12", text: "read wikipedia: wicked witch of the west" },
  { id: "r20", source: "filesys", ts: "08:58:30", text: "~/notes/threat_level.md — created" },
  { id: "r21", source: "screen",  ts: "09:01:08", text: "opened journal — searched 'home'" },
  { id: "r22", source: "email",   ts: "09:03:44", text: "from: uncle.henry@auntiekansas.net — 'em is worried. so am i.'" },
];

export const LABELS: Label[] = [
  { id: "l01", rawId: "r01", text: "journaling session began — subject: home",                         pages: ["interests/journaling"] },
  { id: "l02", rawId: "r02", text: "added 412 words to today's journal",                               pages: ["interests/journaling"] },
  { id: "l03", rawId: "r03", text: "reviewed photos of Toto — strong sentimental signal",              pages: ["people/toto"] },
  { id: "l04", rawId: "r04", text: "received storm warning from neighbor Zeke",                        pages: ["people/zeke"] },
  { id: "l05", rawId: "r05", text: "confirmed Aunt Em's birthday (annual)",                            pages: ["people/aunt-em"] },
  { id: "l06", rawId: "r06", text: "tornado watch active in home county",                              pages: ["interests/farm-life"] },
  { id: "l07", rawId: "r07", text: "researched the Yellow Brick Road",                                 pages: ["projects/get-home-to-kansas"] },
  { id: "l08", rawId: "r08", text: "sketched the Scarecrow — first visual record",                     pages: ["people/scarecrow"] },
  { id: "l09", rawId: "r09", text: "confirmation from Glinda re: ruby slippers",                       pages: ["people/glinda"] },
  { id: "l10", rawId: "r10", text: "researched Tin Man — his predicament noted",                       pages: ["people/tin-man"] },
  { id: "l11", rawId: "r11", text: "scheduled first meeting with Scarecrow",                           pages: ["people/scarecrow"] },
  { id: "l12", rawId: "r12", text: "Tin Man en route — practical support",                             pages: ["people/tin-man"] },
  { id: "l13", rawId: "r13", text: "plan: reach the Emerald City",                                     pages: ["projects/get-home-to-kansas"] },
  { id: "l14", rawId: "r14", text: "journal updated — reflection on the road so far",                  pages: ["interests/journaling"] },
  { id: "l15", rawId: "r15", text: "Aunt Em reports Toto is safe",                                     pages: ["people/aunt-em", "people/toto"] },
  { id: "l16", rawId: "r16", text: "studied the Oz overworld map",                                     pages: ["projects/get-home-to-kansas"] },
  { id: "l17", rawId: "r17", text: "Cowardly Lion joining the party",                                  pages: ["people/cowardly-lion"] },
  { id: "l18", rawId: "r18", text: "audience with the Wizard booked",                                  pages: ["people/wizard-of-oz"] },
  { id: "l19", rawId: "r19", text: "researched the Wicked Witch — threat assessment",                  pages: ["people/wicked-witch-of-the-west"] },
  { id: "l20", rawId: "r20", text: "drafted threat-level note — witch, flying monkeys, water",         pages: ["people/wicked-witch-of-the-west"] },
  { id: "l21", rawId: "r21", text: "journal searched for 'home' — recurring motif",                    pages: ["interests/journaling", "projects/get-home-to-kansas"] },
  { id: "l22", rawId: "r22", text: "Uncle Henry writes — family concern rising",                       pages: ["people/uncle-henry"] },
];

export const WIKI_PAGES: Record<string, WikiPage> = {
  "people/scarecrow": {
    slug: "people/scarecrow",
    dir: "people",
    title: "Scarecrow",
    confidenceStart: 0.30,
    confidenceEnd: 0.82,
    lastUpdated: "2026-04-24",
    lede: "Companion encountered on the Yellow Brick Road, east of the Munchkin country. Animate, articulate, straw-filled; self-describes as lacking a brain.",
    body: [
      { kind: "p", text: "Dorothy lifted him from a pole in a cornfield on the afternoon of her second day in Oz. He walked without prompting once the pole was removed. He speaks in full sentences and has demonstrated problem-solving that contradicts his self-assessment — most notably during the crow incident at Mile 6 — see [[people/tin-man]] for corroborating account." },
      { kind: "p", text: "Current traveling companion. Heading to the Emerald City under the plan to request a brain from [[people/wizard-of-oz]]. Close friends with [[people/tin-man]] and [[people/cowardly-lion]] as of this week." },
      { kind: "updated", date: "2026-04-23", text: "Revised disposition after he demonstrated problem-solving with the crows. Confidence raised from 0.55 → 0.82. Self-description (\"I have no brain\") may be a persistent belief rather than a factual state." },
      { kind: "h", text: "What We Don't Know" },
      { kind: "unknown", items: [
        "Whether he was animated by magic, transformed from a human, or is sui generis.",
        "Where he was prior to the cornfield.",
        "Whether the Wizard can, in fact, grant him what he's looking for.",
      ]},
    ],
  },
  "people/toto": {
    slug: "people/toto",
    dir: "people",
    title: "Toto",
    confidenceStart: 0.80,
    confidenceEnd: 0.95,
    lastUpdated: "2026-04-24",
    lede: "Dorothy's dog. Small, dark, long-term companion. Frequent subject of photographs and journal references.",
    body: [],
  },
  "people/aunt-em": {
    slug: "people/aunt-em",
    dir: "people",
    title: "Aunt Em",
    confidenceStart: 0.70,
    confidenceEnd: 0.90,
    lastUpdated: "2026-04-24",
    lede: "Dorothy's guardian on the Kansas farm. Birthday Nov 30 (annual). Primary emotional tether to home.",
    body: [],
  },
  "people/uncle-henry": {
    slug: "people/uncle-henry",
    dir: "people",
    title: "Uncle Henry",
    confidenceStart: 0.60,
    confidenceEnd: 0.78,
    lastUpdated: "2026-04-24",
    lede: "Co-guardian. Runs the farm with [[people/aunt-em]]. Writes rarely; when he does, it's serious.",
    body: [],
  },
  "people/tin-man": {
    slug: "people/tin-man",
    dir: "people",
    title: "Tin Man",
    confidenceStart: 0.25,
    confidenceEnd: 0.74,
    lastUpdated: "2026-04-24",
    lede: "Former woodcutter, now an articulated tin figure. Requires regular oiling. Traveling with [[people/scarecrow]] and Dorothy.",
    body: [],
  },
  "people/cowardly-lion": {
    slug: "people/cowardly-lion",
    dir: "people",
    title: "Cowardly Lion",
    confidenceStart: 0.20,
    confidenceEnd: 0.68,
    lastUpdated: "2026-04-24",
    lede: "Large feline, reportedly afraid of essentially everything. Has joined the party en route to Emerald City.",
    body: [],
  },
  "people/glinda": {
    slug: "people/glinda",
    dir: "people",
    title: "Glinda",
    confidenceStart: 0.45,
    confidenceEnd: 0.80,
    lastUpdated: "2026-04-24",
    lede: "Good Witch of the South. Provided the ruby slippers. Confident, direct, never fully explains what she knows.",
    body: [],
  },
  "people/wizard-of-oz": {
    slug: "people/wizard-of-oz",
    dir: "people",
    title: "Wizard of Oz",
    confidenceStart: 0.15,
    confidenceEnd: 0.40,
    lastUpdated: "2026-04-24",
    lede: "Ruler of the Emerald City. Identity unclear. Power level unverified. Possibly a man behind a curtain — see log 2026-04-22.",
    body: [],
  },
  "people/wicked-witch-of-the-west": {
    slug: "people/wicked-witch-of-the-west",
    dir: "people",
    title: "Wicked Witch of the West",
    confidenceStart: 0.35,
    confidenceEnd: 0.88,
    lastUpdated: "2026-04-24",
    lede: "Hostile. Operates from Kiamo Ko in the western quadrant. Reported weaknesses: water, sunlight.",
    body: [
      { kind: "p", text: "First identified as a hostile actor on 2026-04-19 after the flying-monkey incident near the Yellow Brick Road. Appears to have jurisdictional overlap with [[people/glinda]] (South) over Oz airspace." },
      { kind: "updated", date: "2026-04-22", text: "Reclassified from 'probable nuisance' to 'active threat' after direct encounter at Kiamo Ko. The 'allergic to water' report is not a rumor — confirmed in vivo. Confidence 0.35 → 0.88." },
    ],
  },
  "people/zeke": {
    slug: "people/zeke",
    dir: "people",
    title: "Zeke",
    confidenceStart: 0.30,
    confidenceEnd: 0.55,
    lastUpdated: "2026-04-24",
    lede: "Neighbor on the Kansas prairie. Storm-watcher. Writes short, urgent emails.",
    body: [],
  },
  "projects/get-home-to-kansas": {
    slug: "projects/get-home-to-kansas",
    dir: "projects",
    title: "Get home to Kansas",
    confidenceStart: 0.60,
    confidenceEnd: 0.95,
    lastUpdated: "2026-04-24",
    lede: "Active. Current plan: reach the Emerald City, consult [[people/wizard-of-oz]]. Ruby slippers confirmed on-person.",
    body: [
      { kind: "p", text: "Entered Oz unplanned on 2026-04-18 via a Cowley County tornado. [[people/glinda]] provided the slippers and pointed toward the Emerald City. Route: Yellow Brick Road, east → southwest → west." },
      { kind: "p", text: "Travel party acquired en route: [[people/scarecrow]] (seeks brain), [[people/tin-man]] (seeks heart), [[people/cowardly-lion]] (seeks courage). All three are traveling to the same destination on adjacent goals." },
    ],
  },
  "interests/farm-life": {
    slug: "interests/farm-life",
    dir: "interests",
    title: "Farm life",
    confidenceStart: 0.70,
    confidenceEnd: 0.85,
    lastUpdated: "2026-04-24",
    lede: "Dominant background signal. Chores, weather, animals. Heavily present in journal entries pre-twister.",
    body: [],
  },
  "interests/journaling": {
    slug: "interests/journaling",
    dir: "interests",
    title: "Journaling",
    confidenceStart: 0.80,
    confidenceEnd: 0.92,
    lastUpdated: "2026-04-24",
    lede: "Daily practice. Often first and last activity of the day. 'Home' is the recurring motif.",
    body: [],
  },
  "people/dorothy-gale": {
    slug: "people/dorothy-gale",
    dir: "people",
    title: "Dorothy Gale",
    confidenceStart: 1.0,
    confidenceEnd: 1.0,
    lastUpdated: "2026-04-24",
    lede: "You.",
    body: [],
  },
};

// Radial layout around Dorothy (600, 360). Clusters:
//   W  — travel party (left)
//   N  — Kansas / family (upper)
//   E  — Oz politics (right)
//   S  — projects / interests (lower)
export const GRAPH_NODES: GraphNode[] = [
  { slug: "people/dorothy-gale",              label: "Dorothy",       x: 600, y: 360, r: 40 },

  // West — travel party
  { slug: "people/scarecrow",                 label: "Scarecrow",     x: 420, y: 278, r: 26 },
  { slug: "people/tin-man",                   label: "Tin Man",       x: 378, y: 360, r: 24 },
  { slug: "people/cowardly-lion",             label: "Lion",          x: 420, y: 442, r: 22 },

  // North — Kansas
  { slug: "people/toto",                      label: "Toto",          x: 528, y: 188, r: 28 },
  { slug: "people/aunt-em",                   label: "Aunt Em",       x: 648, y: 148, r: 26 },
  { slug: "people/uncle-henry",               label: "Uncle Henry",   x: 772, y: 178, r: 22 },
  { slug: "people/zeke",                      label: "Zeke",          x: 860, y: 242, r: 16 },

  // East — Oz
  { slug: "people/glinda",                    label: "Glinda",        x: 820, y: 322, r: 24 },
  { slug: "people/wizard-of-oz",              label: "Wizard",        x: 862, y: 398, r: 20 },
  { slug: "people/wicked-witch-of-the-west",  label: "Witch",         x: 820, y: 480, r: 28 },

  // South — projects & interests
  { slug: "projects/get-home-to-kansas",      label: "Get home",      x: 600, y: 568, r: 34 },
  { slug: "interests/farm-life",              label: "Farm life",     x: 720, y: 528, r: 22 },
  { slug: "interests/journaling",             label: "Journaling",    x: 480, y: 528, r: 22 },
];

export const GRAPH_EDGES: GraphEdge[] = [
  { from: "people/dorothy-gale", to: "people/scarecrow" },
  { from: "people/dorothy-gale", to: "people/tin-man" },
  { from: "people/dorothy-gale", to: "people/cowardly-lion" },
  { from: "people/dorothy-gale", to: "people/glinda" },
  { from: "people/dorothy-gale", to: "people/wizard-of-oz" },
  { from: "people/dorothy-gale", to: "people/toto" },
  { from: "people/dorothy-gale", to: "people/aunt-em" },
  { from: "people/dorothy-gale", to: "people/uncle-henry" },
  { from: "people/dorothy-gale", to: "projects/get-home-to-kansas" },
  { from: "people/dorothy-gale", to: "interests/journaling" },
  { from: "people/dorothy-gale", to: "interests/farm-life" },
  { from: "people/scarecrow", to: "people/tin-man" },
  { from: "people/scarecrow", to: "people/cowardly-lion" },
  { from: "people/scarecrow", to: "people/wizard-of-oz" },
  { from: "people/tin-man", to: "people/cowardly-lion" },
  { from: "people/tin-man", to: "people/wizard-of-oz" },
  { from: "people/glinda", to: "people/wizard-of-oz" },
  { from: "people/glinda", to: "people/wicked-witch-of-the-west" },
  { from: "people/wicked-witch-of-the-west", to: "people/wizard-of-oz" },
  { from: "people/aunt-em", to: "people/uncle-henry" },
  { from: "people/aunt-em", to: "people/toto" },
  { from: "people/aunt-em", to: "people/zeke" },
  { from: "projects/get-home-to-kansas", to: "people/wizard-of-oz" },
  { from: "projects/get-home-to-kansas", to: "people/glinda" },
  { from: "projects/get-home-to-kansas", to: "interests/farm-life" },
  { from: "interests/journaling", to: "projects/get-home-to-kansas" },
  { from: "interests/journaling", to: "interests/farm-life" },
];
