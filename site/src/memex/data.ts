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
    body: [
      { kind: "p", text: "Present in Dorothy's photo library going back to at least August 2024, with new photos added roughly monthly. Appears by name in about a third of her journal entries — more often than any person other than [[people/aunt-em]]." },
      { kind: "p", text: "Not currently in Oz with her. [[people/aunt-em]] confirmed via email on 2026-04-22 that he's physically safe on the farm (\"the dog is fine, come home when you can\"). This is the first direct evidence of his status since the tornado." },
    ],
  },
  "people/aunt-em": {
    slug: "people/aunt-em",
    dir: "people",
    title: "Aunt Em",
    confidenceStart: 0.70,
    confidenceEnd: 0.90,
    lastUpdated: "2026-04-24",
    lede: "Dorothy's guardian on the Kansas farm. Birthday Nov 30 (annual). Primary emotional tether to home.",
    body: [
      { kind: "p", text: "Lives with [[people/uncle-henry]]. Runs the household while he runs the land. Corresponds with Dorothy by email — subject lines are brief and the tone is always practical. First on Dorothy's calendar every November 30." },
      { kind: "p", text: "Central figure in Dorothy's outbound thoughts. When she searches her journal for \"home\", matches cluster around Aunt Em roughly three-to-one over any other person. She is the person Dorothy most consistently wants to get back to." },
      { kind: "updated", date: "2026-04-22", text: "Confirmed Aunt Em and [[people/toto]] are both physically safe after the tornado. Prior working assumption (recorded 2026-04-19) that the farmhouse was destroyed was wrong; only the upper structure is gone. Confidence raised from 0.62 → 0.90." },
    ],
  },
  "people/uncle-henry": {
    slug: "people/uncle-henry",
    dir: "people",
    title: "Uncle Henry",
    confidenceStart: 0.60,
    confidenceEnd: 0.78,
    lastUpdated: "2026-04-24",
    lede: "Co-guardian. Runs the farm with [[people/aunt-em]]. Writes rarely; when he does, it's serious.",
    body: [
      { kind: "p", text: "Manages livestock, crops, and the cellar. Keeps weather counsel with [[people/zeke]]. Writes maybe once a year — his email on 2026-04-24 (\"em is worried. so am i.\") is the first direct message Dorothy has received from him in over six months, which is itself the signal." },
    ],
  },
  "people/tin-man": {
    slug: "people/tin-man",
    dir: "people",
    title: "Tin Man",
    confidenceStart: 0.25,
    confidenceEnd: 0.74,
    lastUpdated: "2026-04-24",
    lede: "Former woodcutter, now an articulated tin figure. Requires regular oiling. Traveling with [[people/scarecrow]] and Dorothy.",
    body: [
      { kind: "p", text: "Met at Mile 4 of the Yellow Brick Road. Was rust-locked standing beside a fallen tree; moved freely within ten minutes of being oiled. Now travels with the party. Self-describes as lacking a heart — the claim is structurally similar to [[people/scarecrow]]'s \"I have no brain\" and may reflect the same self-assessment pattern." },
      { kind: "p", text: "The most tactically useful companion so far — the oil can, and his working knowledge of the woodcutter's trade, translate directly into practical help on the road. Plans to petition [[people/wizard-of-oz]] for a heart." },
    ],
  },
  "people/cowardly-lion": {
    slug: "people/cowardly-lion",
    dir: "people",
    title: "Cowardly Lion",
    confidenceStart: 0.20,
    confidenceEnd: 0.68,
    lastUpdated: "2026-04-24",
    lede: "Large feline, reportedly afraid of essentially everything. Has joined the party en route to Emerald City.",
    body: [
      { kind: "p", text: "Joined the group at the forest's edge after initially charging at them and then immediately apologizing. Confidence in his stated cowardice is moderate at best — behavior under actual threat (the poppy field, most notably) contradicts the self-description more often than it confirms it. Intends to petition [[people/wizard-of-oz]] for courage." },
    ],
  },
  "people/glinda": {
    slug: "people/glinda",
    dir: "people",
    title: "Glinda",
    confidenceStart: 0.45,
    confidenceEnd: 0.80,
    lastUpdated: "2026-04-24",
    lede: "Good Witch of the South. Provided the ruby slippers. Confident, direct, never fully explains what she knows.",
    body: [
      { kind: "p", text: "First contact was in Munchkinland, immediately after the tornado landed. Confirmed Dorothy's slippers via email on 2026-04-18 (\"slippers confirmed, ruby\"). Has jurisdictional overlap with [[people/wicked-witch-of-the-west]]; the dynamic between the two is effectively the central politics of the region." },
      { kind: "p", text: "Appears to know more than she volunteers. Multiple interactions have her providing exactly the information needed, no more, framed as \"you'll figure it out.\" Reads as stylistic rather than obstructionist." },
      { kind: "updated", date: "2026-04-23", text: "Confidence raised from 0.45 → 0.80 after cross-reference with the [[projects/get-home-to-kansas]] plan. Her early interventions line up with what the slippers can actually do — she is operating in good faith." },
    ],
  },
  "people/wizard-of-oz": {
    slug: "people/wizard-of-oz",
    dir: "people",
    title: "Wizard of Oz",
    confidenceStart: 0.15,
    confidenceEnd: 0.40,
    lastUpdated: "2026-04-24",
    lede: "Ruler of the Emerald City. Identity unclear. Power level unverified.",
    body: [
      { kind: "p", text: "Access is gated — audience is scheduled for Thursday 2pm per calendar. Claims about his power vary sharply by source: the green-uniformed soldiers describe him as essentially unlimited; [[people/glinda]] has never directly confirmed that claim, and in fact has been careful never to comment on it." },
      { kind: "p", text: "A journal entry dated 2026-04-22 has Dorothy searching \"the man behind the curtain\" — an early sign she's developing a hypothesis that the Wizard's power is performed rather than literal. Currently unresolved; the Thursday audience should be dispositive." },
      { kind: "unknown", items: [
        "Whether he actually possesses magical power or merely performs it.",
        "What he will ask for in exchange for helping Dorothy and her party.",
        "His origin — no source has produced one, and he has never directly answered the question.",
      ]},
    ],
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
      { kind: "p", text: "Assets include a winged-primate guard, a pack of wolves, and an active surveillance capability (the crystal ball). Personal motivation is specifically Dorothy's ruby slippers — the hostility appears to be instrumental, not ideological." },
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
    body: [
      { kind: "p", text: "Domain is weather and livestock. Emails are always terse (\"storm coming in tomorrow, batten the cellar\"). A practical tether between [[people/uncle-henry]]'s farm and the surrounding county. His last email (2026-04-18, 6 hours pre-tornado) is load-bearing evidence that the storm was forecastable, and that the warning was received." },
    ],
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
    body: [
      { kind: "p", text: "Twelve years of journal entries, almost all dated in Kansas. Recurring themes: the cellar, the hired hands, the livestock, the weather. Not explicitly romanticized — farm life appears matter-of-factly, which is part of why it reads as missed now that Dorothy is away from it." },
      { kind: "p", text: "Strongly co-occurs with [[people/aunt-em]], [[people/uncle-henry]], and [[people/toto]] in entries. The interest isn't \"farming\" in the abstract; it's the specific texture of this particular farm." },
    ],
  },
  "interests/journaling": {
    slug: "interests/journaling",
    dir: "interests",
    title: "Journaling",
    confidenceStart: 0.80,
    confidenceEnd: 0.92,
    lastUpdated: "2026-04-24",
    lede: "Daily practice. Often first and last activity of the day. 'Home' is the recurring motif.",
    body: [
      { kind: "p", text: "Handwritten until mid-2024, digital since. Current file: `~/journal/2026-04-23.md` — 412 words in the morning, another 188 appended after the Yellow Brick Road detour. The [[projects/get-home-to-kansas]] plan shows up in almost every entry since 2026-04-18." },
      { kind: "p", text: "Searches within the journal cluster around \"home\" (73 hits in the last two weeks), [[people/aunt-em]] (38), and [[people/toto]] (27). Only a handful of entries in that window do not reference Kansas at all." },
    ],
  },
  "people/dorothy-gale": {
    slug: "people/dorothy-gale",
    dir: "people",
    title: "Dorothy Gale",
    confidenceStart: 1.0,
    confidenceEnd: 1.0,
    lastUpdated: "2026-04-24",
    lede: "You.",
    body: [
      { kind: "p", text: "This page is the anchor. Every other entry here either describes someone you've encountered, something you're working on, or something that matters to you. The memex is whatever portion of your life is recoverable from what the system has seen; the rest is only what you've told it." },
    ],
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
