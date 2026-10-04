"use strict";

const sampleImage = (name) =>
  `https://api.scryfall.com/cards/named?exact=${encodeURIComponent(name)}&format=image`;

const sampleTypeLines = {
  "Virtue of Loyalty": "Enchantment — Virtue",
  "Imodane's Recruiter": "Creature — Human Knight",
  "Virtue of Persistence": "Enchantment — Virtue",
  "Torch the Tower": "Instant",
  "Candy Grapple": "Instant",
  "Hamlet Glutton": "Creature — Giant",
  "Cut In": "Sorcery",
  "Lord Skitter's Butcher": "Creature — Rat Peasant",
  "Diminisher Witch": "Creature — Human Warlock",
  "Brave the Wilds": "Sorcery",
  "Threadbind Clique // Rip the Seams": "Creature — Faerie",
  "Welcome to Sweettooth": "Enchantment",
  "Redcap Thief": "Creature — Goblin Rogue",
  "Gingerbread Hunter": "Creature — Giant",
  "Eriette's Tempting Apple": "Artifact",
  "Gruff Triplets": "Creature — Giant Warlock",
  "Agatha of the Vile Cauldron": "Legendary Creature — Human Warlock",
  "Agatha's Champion": "Creature — Human Knight",
  "Agatha's Soul Cauldron": "Legendary Artifact",
  "Aquatic Alchemist // Bubble Up": "Creature — Merfolk Wizard",
  "Archive Dragon": "Creature — Dragon",
  "Archon of the Wild Rose": "Creature — Archon",
  "Archon's Glory": "Instant",
  "Armory Mice": "Creature — Mouse Soldier",
  "Ashiok's Reaper": "Creature — Human Warlock",
  "Ashiok, Wicked Manipulator": "Legendary Planeswalker — Ashiok",
  "Ash, Party Crasher": "Legendary Creature — Human Peasant",
  "Asinine Antics": "Instant",
  "A Tale for the Ages": "Enchantment",
  "Back for Seconds": "Sorcery",
  "Barrow Naughty": "Creature — Faerie Warlock",
  "Beanstalk Wurm // Plant Beans": "Creature — Plant Wurm",
  "Belligerent of the Ball": "Creature — Human Peasant",
  "Bellowing Bruiser // Beat a Path": "Creature — Ogre",
  "Beluna Grandsquall // Seek Thrills": "Legendary Creature — Giant Noble",
  "Beluna's Gatekeeper": "Creature — Giant Soldier",
  "Beseech the Mirror": "Sorcery",
  "Besotted Knight // Betroth the Beast": "Creature — Human Knight",
  "Bespoke Battlegarb": "Artifact — Equipment",
  "Bestial Bloodline": "Enchantment — Aura",
  "Bitter Chill": "Enchantment — Aura",
  "Blossoming Tortoise": "Creature — Turtle",
  "Boundary Lands Ranger": "Creature — Human Ranger",
  "Bramble Familiar // Fetch Quest": "Creature — Elemental Raccoon",
  "Break the Spell": "Instant",
};

const sampleCards = [
  ["Virtue of Loyalty", "4oWoW", ["W"], "Rare"],
  ["Imodane's Recruiter", "2oR", ["R"], "Rare"],
  ["Virtue of Persistence", "5oBoB", ["B"], "Mythic"],
  ["Torch the Tower", "R", ["R"], "Common"],
  ["Candy Grapple", "1oB", ["B"], "Common"],
  ["Hamlet Glutton", "3oG", ["G"], "Common"],
  ["Cut In", "3oR", ["R"], "Common"],
  ["Lord Skitter's Butcher", "2oB", ["B"], "Uncommon"],
  ["Diminisher Witch", "2oU", ["U"], "Common"],
  ["Brave the Wilds", "G", ["G"], "Common"],
  ["Threadbind Clique // Rip the Seams", "3oU", ["U", "W"], "Uncommon"],
  ["Welcome to Sweettooth", "1oG", ["G"], "Common"],
  ["Redcap Thief", "2oR", ["R"], "Common"],
  ["Gingerbread Hunter", "3oG", ["G"], "Common"],
  ["Eriette's Tempting Apple", "4", [], "Uncommon"],
  ["Gruff Triplets", "3oGoGoG", ["G"], "Rare"],
  ["Agatha of the Vile Cauldron", "RoG", ["R", "G"], "Mythic"],
  ["Agatha's Champion", "4oG", ["G"], "Uncommon"],
  ["Agatha's Soul Cauldron", "2", [], "Mythic"],
  ["Aquatic Alchemist // Bubble Up", "1oU", ["U"], "Common"],
  ["Archive Dragon", "4oUoU", ["U"], "Uncommon"],
  ["Archon of the Wild Rose", "2oWoW", ["W"], "Rare"],
  ["Archon's Glory", "W", ["W"], "Common"],
  ["Armory Mice", "1oW", ["W"], "Common"],
  ["Ashiok's Reaper", "3oB", ["B"], "Uncommon"],
  ["Ashiok, Wicked Manipulator", "3oBoB", ["B"], "Mythic"],
  ["Ash, Party Crasher", "RoW", ["R", "W"], "Mythic"],
  ["Asinine Antics", "2oUoU", ["U"], "Mythic"],
  ["A Tale for the Ages", "1oW", ["W"], "Common"],
  ["Back for Seconds", "2oB", ["B"], "Uncommon"],
  ["Barrow Naughty", "1oB", ["B"], "Common"],
  ["Beanstalk Wurm // Plant Beans", "4oG", ["G"], "Common"],
  ["Belligerent of the Ball", "2oR", ["R"], "Rare"],
  ["Bellowing Bruiser // Beat a Path", "4oR", ["R"], "Common"],
  ["Beluna Grandsquall // Seek Thrills", "GoUoR", ["G", "U", "R"], "Mythic"],
  ["Beluna's Gatekeeper", "5oU", ["U"], "Common"],
  ["Beseech the Mirror", "1oBoBoB", ["B"], "Mythic"],
  ["Besotted Knight // Betroth the Beast", "3oW", ["W"], "Common"],
  ["Bespoke Battlegarb", "1oR", ["R"], "Common"],
  ["Bestial Bloodline", "1oG", ["G"], "Common"],
  ["Bitter Chill", "1oU", ["U"], "Common"],
  ["Blossoming Tortoise", "2oGoG", ["G"], "Mythic"],
  ["Boundary Lands Ranger", "1oR", ["R"], "Uncommon"],
  ["Bramble Familiar // Fetch Quest", "1oG", ["G"], "Rare"],
  ["Break the Spell", "W", ["W"], "Common"],
].map(([name, manaArena, colors, rarity], index, all) => {
  const score = 38 + ((index * 37 + 13) % 58);
  const grade = (score / 20).toFixed(1);
  const typeLine = sampleTypeLines[name] || "";
  return {
  arenaId: 901 + index,
  name,
  image: sampleImage(name),
  score,
  grade,
  rarity,
  colors,
  manaArena,
  typeLine,
  rank: index + 1,
  rankOf: all.length,
  ratings: [{ source: "Draftsim", grade: Number((Number(grade) - 0.2).toFixed(1)), scale: "0 to 5" }],
  };
});

function seededShuffle(items, seed) {
  const shuffled = [...items];
  let state = seed >>> 0;
  for (let index = shuffled.length - 1; index > 0; index--) {
    state = (state * 1664525 + 1013904223) >>> 0;
    const swapIndex = state % (index + 1);
    [shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]];
  }
  return shuffled;
}

const selectedDraftCards = seededShuffle(sampleCards, 20261003);

const sampleState = {
  version: "history-sample-1",
  set: "WOE",
  draftCompleted: true,
  completedDraftId: "sample-draft",
  status: { demo: true, cardDb: true, logFound: true, updatedAt: null, source: "Sample data" },
  pack: null,
  cards: [],
  takenCards: [],
  history: {
    revision: 2,
    drafts: [{
      id: "sample-draft",
      event: "PremierDraft_WOE",
      started_at: "2026-09-28T18:12:00+00:00",
      updated_at: "2026-09-28T19:06:00+00:00",
      observations: 45,
      packs: 3,
    }],
    sealed: [{
      id: "sample-sealed",
      event: "Sealed_WOE",
      created_at: "2026-09-30T20:34:00+00:00",
      card_count: 90,
    }],
  },
};

const sampleDraft = {
  id: "sample-draft",
  event: "PremierDraft_WOE",
  observations: Array.from({ length: 45 }, (_, index) => {
    const pack = Math.floor(index / 15);
    const pick = index % 15;
    const chosen = selectedDraftCards[index];
    const returned = pick === 7;
    const others = seededShuffle(
      sampleCards.filter((card) => card.arenaId !== chosen.arenaId),
      4100 + index,
    );
    let available;
    let takenCards = [];
    if (returned) {
      const firstPick = selectedDraftCards[pack * 15];
      const returnCards = seededShuffle(
        sampleCards.filter((card) =>
          card.arenaId !== firstPick.arenaId && card.arenaId !== chosen.arenaId,
        ),
        5100 + pack,
      );
      const returnedPack = [
        firstPick,
        ...returnCards.slice(0, 7),
        chosen,
        ...returnCards.slice(7, 13),
      ];
      available = returnedPack.slice(8);
      takenCards = returnedPack.slice(1, 8);
    } else {
      available = [chosen, ...others.slice(0, 14)].slice(0, Math.max(1, 15 - pick));
    }
    return {
      pack,
      pick,
      chosenIds: [chosen.arenaId],
      chosenCards: [chosen],
      cards: available,
      takenCards,
    };
  }),
};

const sampleColorNames = { W: "White", U: "Blue", B: "Black", R: "Red", G: "Green" };
const sampleColorPairs = [
  ["W", "U"], ["W", "B"], ["W", "R"], ["W", "G"], ["U", "B"],
  ["U", "R"], ["U", "G"], ["B", "R"], ["B", "G"], ["R", "G"],
];
const sampleManaValue = (card) => (card.manaArena || "").split("o").reduce((total, symbol) => {
  if (/^\d+$/.test(symbol)) return total + Number(symbol);
  if (symbol.includes("/") && symbol.split("/").some((part) => /^\d+$/.test(part))) {
    return total + Math.max(...symbol.split("/").filter((part) => /^\d+$/.test(part)).map(Number));
  }
  return total + (symbol && symbol.toUpperCase() !== "X" ? 1 : 0);
}, 0);
const sampleBuilds = sampleColorPairs.map((colors) => {
  const eligible = selectedDraftCards.filter((card) =>
    (card.colors || []).every((color) => colors.includes(color)),
  );
  const cards = [...eligible].sort((a, b) =>
    (b.score ?? -1) - (a.score ?? -1)
    || Number(b.typeLine.includes("Creature")) - Number(a.typeLine.includes("Creature"))
    || sampleManaValue(a) - sampleManaValue(b)
    || a.name.localeCompare(b.name),
  ).slice(0, 23);
  const selectedIds = new Set(cards.map((card) => card.arenaId));
  const cuts = selectedDraftCards
    .filter((card) => !selectedIds.has(card.arenaId))
    .sort((a, b) =>
      Number((a.colors || []).some((color) => !colors.includes(color)))
        - Number((b.colors || []).some((color) => !colors.includes(color)))
      || (a.score ?? 101) - (b.score ?? 101)
      || a.name.localeCompare(b.name),
    )
    .slice(0, 8)
    .map((card) => ({
      ...card,
      cutReason: (card.colors || []).some((color) => !colors.includes(color))
        ? "Outside these colors"
        : card.score < 60 ? "Low grade" : "Below the top 23",
    }));
  const manaValues = cards.map(sampleManaValue);
  const creatures = cards.filter((card) => card.typeLine.includes("Creature")).length;
  const early = manaValues.filter((value) => value <= 2).length;
  const topEnd = manaValues.filter((value) => value >= 5).length;
  const curveCounts = new Map();
  for (const value of manaValues) curveCounts.set(value, (curveCounts.get(value) || 0) + 1);
  const pips = {};
  for (const card of cards) {
    for (const symbol of card.manaArena.split("o")) {
      for (const color of "WUBRG") {
        if (symbol.includes(color)) pips[color] = (pips[color] || 0) + 1;
      }
    }
  }
  const name = colors.map((color) => sampleColorNames[color]).join("-");
  const averageScore = cards.length
    ? Math.round(cards.reduce((sum, card) => sum + card.score, 0) / cards.length * 10) / 10
    : null;
  return {
    colors,
    name,
    tier: null,
    eligibleCount: eligible.length,
    averageScore,
    cards,
    cuts,
    balance: {
      checks: [
        { label: "Spell count", value: `${cards.length}/23`, status: cards.length === 23 ? "good" : "warning", detail: "Limited decks usually play 23 nonland cards." },
        { label: "Creatures", value: String(creatures), status: creatures >= 14 && creatures <= 17 ? "good" : "warning", detail: "A common target is 14–17 creatures." },
        { label: "Early plays", value: String(early), status: early >= 6 ? "good" : "warning", detail: "Cards costing 1–2 mana; fewer than 6 may leave a slow start." },
        { label: "Top end", value: String(topEnd), status: topEnd <= 5 ? "good" : "warning", detail: "Cards costing 5+ mana; too many can clog your hand." },
      ],
      curve: [...curveCounts].sort((a, b) => a[0] - b[0]).map(([manaValue, count]) => ({ manaValue, count })),
      knownManaCosts: cards.length,
      pips,
    },
    _rank: [
      (averageScore || 0) * cards.length / 23 + cards.length * 0.15
        + cards.filter((card) => card.colors.length).length * 0.05,
      cards.length,
      cards.filter((card) => card.colors.length).length,
    ],
  };
});
sampleBuilds.sort((a, b) =>
  b._rank[0] - a._rank[0] || b._rank[1] - a._rank[1] || b._rank[2] - a._rank[2]
  || a.name.localeCompare(b.name),
);
sampleDraft.deckBuild = {
  builds: sampleBuilds.map(({ _rank, ...build }) => build),
};

const sampleSealed = {
  id: "sample-sealed",
  event: "Sealed_WOE",
  createdAt: "2026-09-30T20:34:00+00:00",
  cardCount: 90,
  cards: [
    { name: "Virtue of Loyalty", image: sampleImage("Virtue of Loyalty"), count: 1, score: 94, grade: "4.7", colors: ["W"], manaArena: "3oWoW", typeLine: "Enchantment — Virtue", ratings: [] },
    { name: "Imodane's Recruiter", image: sampleImage("Imodane's Recruiter"), count: 2, score: 88, grade: "4.4", colors: ["R"], manaArena: "2oR", typeLine: "Creature — Human Knight", ratings: [] },
    { name: "Cut In", image: sampleImage("Cut In"), count: 2, score: 76, grade: "3.8", colors: ["R"], manaArena: "3oR", typeLine: "Sorcery", ratings: [] },
    { name: "Diminisher Witch", image: sampleImage("Diminisher Witch"), count: 1, score: 72, grade: "3.6", colors: ["B"], manaArena: "2oB", typeLine: "Creature — Human Warlock", ratings: [] },
    { name: "Redcap Thief", image: sampleImage("Redcap Thief"), count: 3, score: 63, grade: "3.2", colors: ["R"], manaArena: "2oR", typeLine: "Creature — Goblin Rogue", ratings: [] },
    { name: "Threadbind Clique", image: sampleImage("Threadbind Clique"), count: 1, score: 70, grade: "3.5", colors: ["U"], manaArena: "3oU", typeLine: "Creature — Faerie", ratings: [] },
    { name: "Welcome to Sweettooth", image: sampleImage("Welcome to Sweettooth"), count: 1, score: 67, grade: "3.4", colors: ["G"], manaArena: "1oG", typeLine: "Enchantment", ratings: [] },
    { name: "Plains", image: sampleImage("Plains"), count: 4, score: null, grade: null, colors: [], manaArena: "", typeLine: "Basic Land — Plains", isLand: true, ratings: [] },
  ],
};

const nativeFetch = window.fetch.bind(window);
window.fetch = async (input, options) => {
  const path = new URL(typeof input === "string" ? input : input.url, location.href).pathname;
  if (path === "/api/state") return Response.json(sampleState);
  if (path === "/api/history/draft/sample-draft") return Response.json(sampleDraft);
  if (path === "/api/history/sealed/sample-sealed") return Response.json(sampleSealed);
  return nativeFetch(input, options);
};

setTimeout(() => document.querySelector('#draft-tabs [data-view="history"]')?.click(), 0);
