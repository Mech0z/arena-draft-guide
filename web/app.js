"use strict";
const POLL_MS = 1000;
let lastVersion = null;
let currentState = null;
let activeView = "draft";
let expandedSealedPair = null;
let expandedSealedMode = null;
let sealedArchetypeLimit = 5;
const AGGREGATE_RATING = "__aggregate__";
let selectedRatingSource = AGGREGATE_RATING;
let historySelection = null;
let historyDetail = null;
let historyLoading = false;
let historyError = null;
let replayIndex = 0;
let selectedDeckPair = null;
let autoOpenedCompletedDraftId = null;

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function scoreColor(score) {
  const hue = Math.max(0, Math.min(120, ((score - 30) / 65) * 120));
  return `hsl(${hue}, 70%, 55%)`;
}

function renderCard(card, isBest) {
  const root = el("article", "card"
    + (isBest ? " best" : "")
    + (card.unrated ? " unrated" : "")
    + (card.takenByOthers ? " taken" : "")
    + (card.chosen ? " chosen" : ""));
  if (card.image) {
    const img = el("img");
    img.src = card.image;
    img.alt = card.name;
    root.append(img);
  }
  const body = el("div", "body");
  const head = el("div", "head");
  if (!card.unrated) {
    const score = el("div", "score", card.score === null ? "–" : (card.grade || Math.round(card.score)));
    if (card.score !== null) score.style.background = scoreColor(card.score);
    head.append(score);
  }
  if (card.pickOrder) {
    const pick = el("div", "score pick-score", card.pickOrder.rarity[0].toUpperCase() + "#" + card.pickOrder.rank);
    pick.style.background = scoreColor(card.pickOrder.score);
    pick.title = `Untapped.gg pick order: #${card.pickOrder.rank} of ${card.pickOrder.rankOf} ${card.pickOrder.rarity}s (avg pick ${card.pickOrder.avgPick.toFixed(1)})`;
    head.append(pick);
  }
  const title = el("div", "title");
  title.append(el("div", "name", card.name));
  const rankText = card.unrated
    ? (card.unratedMessage || "No rating found")
    : (card.score === null ? "Not enough data" : card.sourceRank
      ? `#${card.rank} of ${card.rankOf} in pack`
      : `#${card.rank} of ${card.rankOf}`);
  title.append(el("div", "sub", rankText + (card.rarity ? " \u00b7 " + card.rarity : "")));
  if (card.manaArena) title.querySelector(".sub").append(" ", manaEl(card.manaArena));
  head.append(title);
  body.append(head);
  if ((card.topPicks || []).length) {
    const badges = el("div", "badges");
    for (const label of card.topPicks) badges.append(el("span", "badge", label));
    body.append(badges);
  }

  const texts = el("div", "texts");
  for (const r of card.ratings || []) {
    const numericScale = typeof r.scale === "string" ? r.scale.match(/^0(?:\.0)?\s*to\s*(\d+(?:\.0)?)$/) : null;
    const detail = r.grade !== null && r.grade !== undefined
      ? String(r.grade) + (numericScale ? `/${numericScale[1].replace(/\.0$/, "")}` : "")
      : r.comment;
    if (!detail) continue;
    const p = el("p", "");
    const source = el(r.sourceUrl && r.sourceUrl.startsWith("https://") ? "a" : "b", "", r.source + ":");
    if (source.tagName === "A") {
      source.href = r.sourceUrl;
      source.target = "_blank";
      source.rel = "noreferrer";
    }
    p.append(source, document.createTextNode(" " + detail));
    texts.append(p);
  }
  for (const n of card.notes || []) {
    const p = el("p", "");
    p.append(el("b", "", n.source + ": "), document.createTextNode(n.text));
    texts.append(p);
  }
  body.append(texts);
  root.append(body);
  return root;
}

function pct(x) {
  return (x * 100).toFixed(x >= 0.1 ? 1 : 2) + "%";
}

const preview = (() => {
  const box = el("div", "preview");
  const img = el("img");
  box.append(img);
  document.body.append(box);
  const place = (e) => {
    const w = box.offsetWidth || 300, h = box.offsetHeight || 420;
    const x = e.clientX + 20 + w > innerWidth ? e.clientX - 20 - w : e.clientX + 20;
    const y = Math.max(4, Math.min(e.clientY - h / 2, innerHeight - h - 4));
    box.style.left = x + "px";
    box.style.top = y + "px";
  };
  return {
    show(src, e) { if (img.getAttribute("src") !== src) img.src = src; box.style.display = "block"; place(e); },
    move: place,
    hide() { box.style.display = "none"; },
  };
})();

function manaEl(text) {
  const box = el("span", "mana");
  for (const sym of (text || "").split("o").filter(Boolean)) {
    const s = sym.replace(/[()]/g, "");
    const colors = s.split("/").filter((x) => /^[WUBRG]$/.test(x));
    const pip = el("span", "pip " + (colors.length > 1 ? "multi" : colors.length ? "c" + colors[0] : "cgen"), colors.length ? colors.join("") : s);
    if (colors.length > 1) pip.style.background = `linear-gradient(135deg, var(--m${colors[0]}) 50%, var(--m${colors[1]}) 50%)`;
    box.append(pip);
  }
  return box;
}

function renderInstants(ins) {
  const box = document.getElementById("instants");
  box.replaceChildren();
  if (!ins) { box.hidden = true; return; }
  box.hidden = false;
  const head = el("div", "ihead");
  head.append(el("b", "", "Opponent instant-speed"),
    document.createTextNode(` · limited-set candidates · ${ins.untapped} of ${ins.lands} lands untapped · colours ${ins.colours || "unknown"}`));
  box.append(head);
  const row = el("div", "irow");
  const add = (list, label) => {
    if (!list.length) return;
    if (label) row.append(el("span", "ilabel", label));
    for (const c of list) {
      const item = el("div", "icard" + (c.castable ? "" : " locked"));
      const img = el("img");
      img.src = c.image;
      img.alt = c.name;
      item.append(img, el("span", "iname", c.name), manaEl(c.mana));
      item.addEventListener("mouseenter", (e) => preview.show(c.image, e));
      item.addEventListener("mousemove", (e) => preview.move(e));
      item.addEventListener("mouseleave", () => preview.hide());
      row.append(item);
    }
  };
  add(ins.shown, "Seen from opponent");
  add(ins.possible, "Possible from limited set");
  if (!row.children.length) row.append(el("span", "ilabel", "Nothing castable with current untapped mana."));
  box.append(row);
}

function setArchetypesOpen(open) {
  const panel = document.getElementById("archetypes");
  const toggle = document.getElementById("archetypes-toggle");
  panel.hidden = !open;
  document.body.classList.toggle("archetypes-open", open);
  toggle.setAttribute("aria-expanded", String(open));
}

function archetypeTierRank(tier) {
  if (tier === null || tier === undefined || tier === "") return Number.POSITIVE_INFINITY;
  const value = String(tier).trim().toUpperCase().replace(/^TIER\s*/, "");
  const tierOrder = ["S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "F"];
  const letterRank = tierOrder.indexOf(value);
  if (letterRank !== -1) return letterRank;
  const numericTier = Number(value.replace(/^T/, ""));
  return Number.isFinite(numericTier) ? 100 + numericTier : Number.POSITIVE_INFINITY;
}

function archetypeTierClass(tier) {
  if (tier === null || tier === undefined || tier === "") return "tier-unrated";
  const value = String(tier).trim().toUpperCase().replace(/^TIER\s*/, "");
  if (["S", "A", "A+"].includes(value) || value === "1") return "tier-good";
  if (["B", "B+"].includes(value) || value === "2") return "tier-okay";
  if (["C", "C+", "B-"].includes(value) || value === "3") return "tier-mid";
  if (["D", "D-", "D+", "F"].includes(value) || ["4", "5"].includes(value)) return "tier-bad";
  return "tier-unrated";
}

function compareArchetypes(a, b) {
  const tierA = archetypeTierRank(a.tier);
  const tierB = archetypeTierRank(b.tier);
  if (tierA !== tierB) return tierA < tierB ? -1 : 1;
  const winRateDifference = (b.sixPlusWinRate ?? -1) - (a.sixPlusWinRate ?? -1);
  if (winRateDifference) return winRateDifference;
  return (b.matches ?? -1) - (a.matches ?? -1);
}

function renderArchetypes(guide, inGame) {
  const panel = document.getElementById("archetypes");
  const toggle = document.getElementById("archetypes-toggle");
  const wasOpen = !panel.hidden;
  panel.replaceChildren();
  toggle.hidden = inGame || activeView === "tiers" || !guide || !guide.archetypes || !guide.archetypes.length;
  if (toggle.hidden) {
    setArchetypesOpen(false);
    return;
  }

  const header = el("div", "archetypes-head");
  header.append(el("div", "archetypes-title", `${guide.set.name} archetypes`));
  const close = el("button", "", "Close");
  close.type = "button";
  close.addEventListener("click", () => { panel.hidden = true; });
  header.append(close);
  panel.append(header);

  const list = el("div", "archetype-list");
  const sorted = guide.archetypes.map((archetype, index) => ({ archetype, index }))
    .sort((a, b) => compareArchetypes(a.archetype, b.archetype) || a.index - b.index);
  for (const { archetype } of sorted) {
    const card = el("article", "archetype");
    const top = el("div", "archetype-top");
    top.append(manaEl(archetype.colors.map((color) => "o" + color).join("")), el("h2", "", archetype.name));
    const tierLabel = archetype.tier ? (/^tier\b/i.test(String(archetype.tier)) ? archetype.tier : "Tier " + archetype.tier) : "No tier";
    top.append(el("span", "archetype-tier " + archetypeTierClass(archetype.tier), tierLabel));
    if (archetype.tierSource) {
      const link = el("a", "tier-source", "source");
      link.href = archetype.tierSource;
      link.target = "_blank";
      link.rel = "noreferrer";
      top.append(link);
    }
    card.append(top);
    if (archetype.sixPlusWinRate !== undefined || archetype.matches !== undefined) {
      const stats = el("div", "archetype-stats");
      if (archetype.sixPlusWinRate !== undefined) stats.append(el("span", "", `6+ wins ${archetype.sixPlusWinRate.toFixed(1)}%`));
      if (archetype.matches !== undefined) stats.append(el("span", "", `${archetype.matches.toLocaleString()} matches`));
      card.append(stats);
    }
    card.append(el("p", "", archetype.focus));
    list.append(card);
  }
  panel.append(list);

  if (guide.sources && guide.sources.length) {
    const sources = el("div", "archetype-sources");
    sources.append(document.createTextNode("Sources: "));
    guide.sources.forEach((source, i) => {
      if (i) sources.append(document.createTextNode(" · "));
      const link = el("a", "", source.name);
      link.href = source.url;
      link.target = "_blank";
      link.rel = "noreferrer";
      sources.append(link);
    });
    panel.append(sources);
  }
  setArchetypesOpen(wasOpen);
}

function renderColorTiers(guide) {
  const cards = document.getElementById("cards");
  cards.className = "tier-list-view";
  cards.replaceChildren();
  const table = el("table", "tier-table");
  const head = el("thead");
  const header = el("tr");
  for (const label of ["Tier", "Colors", "Archetype", "6+ wins", "Matches"]) {
    header.append(el("th", "", label));
  }
  head.append(header);
  table.append(head);

  const body = el("tbody");
  const sorted = guide.archetypes.map((archetype, index) => ({ archetype, index }))
    .sort((a, b) => compareArchetypes(a.archetype, b.archetype) || a.index - b.index);
  for (const { archetype } of sorted) {
    const row = el("tr");
    row.append(el("td", "tier-rating " + archetypeTierClass(archetype.tier), archetype.tier ? "Tier " + archetype.tier : "—"));
    const colors = el("td");
    colors.append(manaEl(archetype.colors.map((color) => "o" + color).join("")));
    row.append(colors, el("td", "", archetype.name));
    row.append(el("td", "", archetype.sixPlusWinRate === undefined ? "—" : archetype.sixPlusWinRate.toFixed(1) + "%"));
    row.append(el("td", "", archetype.matches === undefined ? "—" : archetype.matches.toLocaleString()));
    body.append(row);
  }
  table.append(body);
  cards.append(table);
}

function sealedColorGroup(card) {
  const colors = card.colors || [];
  if (colors.length > 1) return "Multicolor";
  if (colors.length === 1) return colors[0];
  return "Colorless";
}

function sealedArchetypeKey(archetype) {
  return [...(archetype.colors || [])].sort().join("");
}

function isEligiblePoolCard(card, archetype) {
  if (card.isLand) return false;
  const colors = card.colors || [];
  return colors.length === 0 || colors.every((color) => archetype.colors.includes(color));
}

function renderPoolCard(card) {
  const item = el("article", "pool-card");
  if (card.image) {
    const img = el("img");
    img.src = card.image;
    img.alt = card.name;
    item.append(img);
    item.addEventListener("mouseenter", (event) => preview.show(card.image, event));
    item.addEventListener("mousemove", (event) => preview.move(event));
    item.addEventListener("mouseleave", () => preview.hide());
  }
  const body = el("div", "pool-card-body");
  const header = el("div", "pool-card-head");
  const title = el("span", "pool-card-name", card.name + (card.count > 1 ? ` ×${card.count}` : ""));
  header.append(title);
  if (card.score !== null && card.score !== undefined) {
    const score = el("span", "pool-score", card.grade || Math.round(card.score));
    score.style.background = scoreColor(card.score);
    header.append(score);
  } else {
    header.append(el("span", "pool-score pool-unrated", "—"));
  }
  if (card.pickOrder) {
    const pick = el("span", "pool-score", card.pickOrder.rarity[0].toUpperCase() + "#" + card.pickOrder.rank);
    pick.style.background = scoreColor(card.pickOrder.score);
    pick.title = `Untapped.gg pick order: #${card.pickOrder.rank} of ${card.pickOrder.rankOf} ${card.pickOrder.rarity}s (avg pick ${card.pickOrder.avgPick.toFixed(1)})`;
    header.append(pick);
  }
  body.append(header);
  if (card.manaArena) body.append(manaEl(card.manaArena));
  if (card.typeLine) body.append(el("span", "pool-type", card.typeLine));
  const ratings = el("div", "pool-ratings");
  for (const rating of card.ratings || []) {
    const numericScale = typeof rating.scale === "string"
      ? rating.scale.match(/^0(?:\.0)?\s*to\s*(\d+(?:\.0)?)$/)
      : null;
    const grade = rating.grade !== null && rating.grade !== undefined
      ? String(rating.grade) + (numericScale ? `/${numericScale[1].replace(/\.0$/, "")}` : "")
      : rating.comment;
    if (!grade) continue;
    const row = el("span", "pool-rating");
    const source = el(rating.sourceUrl && rating.sourceUrl.startsWith("https://") ? "a" : "b", "", rating.source);
    if (source.tagName === "A") {
      source.href = rating.sourceUrl;
      source.target = "_blank";
      source.rel = "noreferrer";
    }
    row.append(source, document.createTextNode(" " + grade));
    ratings.append(row);
  }
  body.append(ratings);
  item.append(body);
  return item;
}

function renderSealedPool(pool) {
  renderInstants(null);
  const cards = document.getElementById("cards");
  cards.className = "sealed-view";
  cards.replaceChildren();
  document.getElementById("pickinfo").textContent =
    `${pool.event} · Sealed pool · ${pool.cardCount} cards (${pool.uniqueCount} unique)`;

  const selectedArchetype = (pool.archetypes || []).find(
    (archetype) => sealedArchetypeKey(archetype) === expandedSealedPair,
  ) || null;
  if (!selectedArchetype) {
    expandedSealedPair = null;
    expandedSealedMode = null;
  }

  const overview = el("section", "sealed-overview");
  overview.append(el("div", "sealed-legend",
    `Pool fit is heuristic: bomb ≥${pool.scoreThresholds.bomb}, strong ≥${pool.scoreThresholds.strong}, playable ≥${pool.scoreThresholds.playable}; archetype tiers come from the set guide.`));
  if (pool.archetypes && pool.archetypes.length) {
    const controls = el("div", "sealed-analysis-controls");
    const label = el("label", "", "Show best-supported");
    const limit = el("select", "sealed-analysis-limit");
    limit.setAttribute("aria-label", "Number of best-supported archetypes to show");
    for (const [value, text] of [["5", "Top 5"], ["10", "Top 10"], ["0", "All"]]) {
      const option = el("option", "", text);
      option.value = value;
      limit.append(option);
    }
    limit.value = String(sealedArchetypeLimit);
    limit.addEventListener("change", () => {
      sealedArchetypeLimit = Number(limit.value);
      expandedSealedPair = null;
      expandedSealedMode = null;
      render(currentState);
    });
    label.append(" ", limit);
    const shownCount = sealedArchetypeLimit ? Math.min(sealedArchetypeLimit, pool.archetypes.length) : pool.archetypes.length;
    controls.append(label, el("span", "", `Showing ${shownCount} of ${pool.archetypes.length}`));
    overview.append(controls);

    const analysis = el("div", "sealed-analysis-grid");
    const visibleArchetypes = sealedArchetypeLimit
      ? pool.archetypes.slice(0, sealedArchetypeLimit)
      : pool.archetypes;
    for (const archetype of visibleArchetypes) {
      const card = el("article", "sealed-analysis");
      const selected = sealedArchetypeKey(archetype) === expandedSealedPair;
      if (selected) card.classList.add("selected");
      const top = el("div", "sealed-analysis-head");
      top.append(manaEl(archetype.colors.map((color) => "o" + color).join("")),
        el("strong", "", archetype.name),
        el("span", "archetype-tier " + archetypeTierClass(archetype.tier), archetype.tier ? "Tier " + archetype.tier : "No tier"));
      card.append(top, el("div", "sealed-potential potential-" + archetype.potentialRank, archetype.potential));
      const stats = el("div", "sealed-fit-stats");
      stats.append(el("span", "", `${archetype.bombs} bombs`),
        el("span", "", `${archetype.strong} strong`),
        el("span", "", `${archetype.playables} playables (${archetype.playableCreatures} creatures, ${archetype.playableNoncreatures} non-creatures)`),
        el("span", "", `${archetype.eligibleCards} eligible`));
      if (archetype.top23Average !== null) {
        stats.append(el("span", "", `top-card avg ${archetype.top23Average}`));
      }
      const actions = el("div", "sealed-analysis-actions");
      for (const [mode, text] of [["eligible", "Show eligible cards"], ["top", "Show top cards"]]) {
        const button = el("button", "sealed-expand", text);
        button.type = "button";
        button.setAttribute("aria-pressed", String(selected && expandedSealedMode === mode));
        button.addEventListener("click", () => {
          if (selected && expandedSealedMode === mode) {
            expandedSealedPair = null;
            expandedSealedMode = null;
          } else {
            expandedSealedPair = sealedArchetypeKey(archetype);
            expandedSealedMode = mode;
          }
          render(currentState);
        });
        actions.append(button);
      }
      card.append(stats, actions);
      analysis.append(card);
    }
    overview.append(analysis);
  }
  cards.append(overview);

  const selectedCards = selectedArchetype
    ? pool.cards.filter((card) =>
      isEligiblePoolCard(card, selectedArchetype)
        && (expandedSealedMode !== "top" || card.score >= pool.scoreThresholds.playable))
    : pool.cards;
  const poolHeading = el("div", "sealed-pool-heading");
  poolHeading.append(el("h2", "", selectedArchetype
    ? `${expandedSealedMode === "top" ? "Top cards" : "Eligible cards"} · ${selectedArchetype.name} · ${selectedCards.reduce((sum, card) => sum + card.count, 0)} copies`
    : "Full sealed pool"));
  if (selectedArchetype) {
    const restore = el("button", "sealed-expand", "Show full pool");
    restore.type = "button";
    restore.addEventListener("click", () => {
      expandedSealedPair = null;
      expandedSealedMode = null;
      render(currentState);
    });
    poolHeading.append(restore);
  }
  cards.append(poolHeading);

  const labels = { W: "White", U: "Blue", B: "Black", R: "Red", G: "Green", Multicolor: "Multicolor", Colorless: "Colorless" };
  const order = ["W", "U", "B", "R", "G", "Multicolor", "Colorless"];
  const grouped = new Map(order.map((key) => [key, []]));
  for (const card of selectedCards) grouped.get(sealedColorGroup(card)).push(card);
  const sections = el("div", "sealed-color-sections");
  if (selectedArchetype && !selectedCards.length) {
    sections.append(el("div", "empty", "No playable-or-better rated cards are eligible for this archetype."));
  }
  for (const key of order) {
    const group = grouped.get(key);
    if (!group.length) continue;
    group.sort((a, b) => (b.score ?? -1) - (a.score ?? -1) || a.name.localeCompare(b.name));
    const section = el("section", "sealed-color-group");
    const cardCount = group.reduce((sum, card) => sum + card.count, 0);
    const creatureCount = group
      .filter((card) => (card.typeLine || "").toLowerCase().includes("creature"))
      .reduce((sum, card) => sum + card.count, 0);
    section.append(el("h2", "", `${labels[key]} · ${cardCount} cards (${creatureCount} creatures, ${cardCount - creatureCount} non-creatures)`));
    const list = el("div", "pool-cards");
    group.forEach((card) => list.append(renderPoolCard(card)));
    section.append(list);
    sections.append(section);
  }
  if (!sections.children.length) sections.append(el("div", "empty", "No eligible cards in this sealed pool."));
  cards.append(sections);
}

function renderLibrary(state) {
  renderInstants(state.game.instants);
  const g = state.game;
  const cards = document.getElementById("cards");
  cards.className = "library";
  cards.replaceChildren();
  document.getElementById("pickinfo").textContent =
    `In game · Library ${g.libraryCount} of ${g.deckSize} cards` + (g.consistent ? "" : " · count may be off");
  const groups = [["Spells", g.cards.filter((c) => !c.isLand)], ["Lands", g.cards.filter((c) => c.isLand)]];
  for (const [title, list] of groups) {
    if (!list.length) continue;
    const total = list.reduce((s, c) => s + c.count, 0);
    const col = el("section", "libgroup");
    col.append(el("h2", "", `${title} · ${total} left · ${pct(g.libraryCount ? total / g.libraryCount : 0)}`));
    for (const c of list) {
      const row = el("div", "librow");
      const nameBox = el("span", "lname");
      nameBox.append(el("span", "lnm", c.name), manaEl(c.mana));
      if (c.typeLine) nameBox.append(el("span", "ltype", c.typeLine));
      row.append(el("span", "cnt", c.count + "×"), nameBox, el("span", "chance", pct(c.chance)));
      const bar = el("span", "bar");
      bar.style.width = Math.min(100, c.chance * 100 * 4) + "%";
      row.append(bar);
      row.addEventListener("mouseenter", (e) => preview.show(c.image, e));
      row.addEventListener("mousemove", (e) => preview.move(e));
      row.addEventListener("mouseleave", () => preview.hide());
      col.append(row);
    }
    cards.append(col);
  }
}

function render(state) {
  const previousState = currentState;
  currentState = state;
  updateRatingSourceControl(state);
  if (!state.sealedPool) {
    expandedSealedPair = null;
    expandedSealedMode = null;
  }
  if (state.sealedPool && !previousState?.sealedPool && !state.game && !state.pack) activeView = "sealed";
  if (!state.sealedPool && activeView === "sealed") activeView = state.game ? "library" : "draft";
  if (state.game && activeView === "draft") activeView = "library";
  if (!state.game && activeView === "library") activeView = state.sealedPool ? "sealed" : "draft";
  if (state.completedDraftId && state.completedDraftId !== autoOpenedCompletedDraftId) {
    autoOpenedCompletedDraftId = state.completedDraftId;
    activeView = "history";
    historySelection = { kind: "draft", id: state.completedDraftId };
    historyDetail = null;
    historyLoading = true;
    historyError = null;
    replayIndex = 0;
    selectedDeckPair = null;
    setTimeout(() => {
      if (currentState?.completedDraftId === state.completedDraftId) {
        loadHistoryEntry("draft", state.completedDraftId);
      }
    }, 0);
  }
  preview.hide();
  renderArchetypes(state.archetypes, Boolean(state.game));
  const tabs = document.getElementById("draft-tabs");
  const draftTab = tabs.querySelector('[data-view="draft"]');
  const tiersTab = tabs.querySelector('[data-view="tiers"]');
  const sealedTab = tabs.querySelector('[data-view="sealed"]');
  const libraryTab = tabs.querySelector('[data-view="library"]');
  const historyTab = tabs.querySelector('[data-view="history"]');
  const hasTiers = Boolean(state.archetypes && state.archetypes.archetypes.length);
  draftTab.hidden = Boolean(state.game);
  tiersTab.hidden = !hasTiers;
  sealedTab.hidden = !state.sealedPool;
  libraryTab.hidden = !state.game;
  historyTab.hidden = false;
  tabs.hidden = false;
  tabs.querySelectorAll("[role=tab]").forEach((tab) => {
    tab.setAttribute("aria-selected", String(tab.dataset.view === activeView));
  });
  if (!state.game) renderInstants(null);
  if (activeView === "sealed" && state.sealedPool) return renderSealedPool(state.sealedPool);
  if (activeView === "tiers" && state.archetypes) return renderColorTiers(state.archetypes);
  if (activeView === "history") return renderHistory(state.history || { drafts: [], sealed: [] });
  if (state.game) return renderLibrary(state);
  document.getElementById("cards").className = "";
  const cards = document.getElementById("cards");
  cards.replaceChildren();
  const info = document.getElementById("pickinfo");
  const p = state.pack;
  info.textContent = p ? [p.event, p.pack && `Pack ${p.pack}`, p.pick && `Pick ${p.pick}`, `${state.cards.length} cards`, state.takenCards?.length && `${state.takenCards.length} taken by others`].filter(Boolean).join(" · ") : "";
  if (!state.cards.length) {
    cards.append(el("div", "empty", state.status.logFound
      ? state.sealedPool
        ? "No draft pack is active. This is a sealed pool, not a draft; use the Sealed pool tab to view it."
        : "Waiting for a draft pack… open a pack in Arena and it will appear here."
      : "Arena Player.log not found."));
    return;
  }
  const rankedPack = cardsForRatingSource([...(state.cards || []), ...(state.takenCards || [])]);
  const displayCards = rankedPack.filter((card) => !card.takenByOthers);
  const takenCards = rankedPack.filter((card) => card.takenByOthers);
  const bestScore = Math.max(...displayCards.map((c) => (c.unrated ? -1 : c.score ?? -1)));
  displayCards.forEach((card) => cards.append(renderCard(card, !card.unrated && card.score === bestScore)));
  for (const card of takenCards) cards.append(renderCard(card, false));
}

function historyLabel(kind, item) {
  return kind === "draft"
    ? `Draft · ${item.event || "Unknown event"}`
    : `Sealed · ${item.event || "Unknown event"} · ${item.card_count} cards`;
}

function historyDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function renderHistory(history) {
  const main = document.getElementById("cards");
  main.className = "history-view";
  main.replaceChildren();
  const list = el("aside", "history-list");
  list.append(el("h2", "", "Saved runs"));
  const items = [
    ...history.drafts.map((item) => ({ kind: "draft", item, date: item.started_at })),
    ...history.sealed.map((item) => ({ kind: "sealed", item, date: item.created_at })),
  ].sort((a, b) => (b.date || "").localeCompare(a.date || ""));
  for (const entry of items) {
    const button = el("button", "history-entry");
    button.type = "button";
    button.setAttribute("aria-selected", String(
      historySelection?.kind === entry.kind && historySelection.id === entry.item.id,
    ));
    button.append(el("span", "", historyLabel(entry.kind, entry.item)));
    button.append(el("span", "history-date",
      `${historyDate(entry.date)}${entry.kind === "draft" ? ` · ${entry.item.observations} picks` : ""}`,
    ));
    button.addEventListener("click", () => loadHistoryEntry(entry.kind, entry.item.id));
    list.append(button);
  }
  main.append(list);

  const detail = el("section", "history-detail");
  if (!historySelection) {
    detail.append(el("div", "empty", items.length
      ? "Choose a saved draft to replay or a sealed pool to inspect."
      : "No saved drafts or sealed pools yet. New runs will be saved here automatically."));
  } else if (historyLoading) {
    detail.append(el("div", "empty", "Loading saved history…"));
  } else if (historyError) {
    detail.append(el("div", "empty", historyError));
  } else if (!historyDetail) {
    detail.append(el("div", "empty", "No saved history was returned."));
  } else {
    const back = el("button", "history-back", "Back to history");
    back.type = "button";
    back.addEventListener("click", () => {
      historySelection = null;
      historyDetail = null;
      render(currentState);
    });
    detail.append(back);
    if (historySelection.kind === "draft") renderDraftReplay(detail, historyDetail);
    else renderSealedHistory(detail, historyDetail);
  }
  main.append(detail);
}

function renderDeckAnalysis(container, deckBuild) {
  const builds = deckBuild?.builds || [];
  if (!builds.length) return;
  const pairKey = (build) => build.colors.join("");
  const selected = builds.find((build) => pairKey(build) === selectedDeckPair) || builds[0];
  selectedDeckPair = pairKey(selected);

  const section = el("section", "deck-analysis");
  const heading = el("div", "deck-analysis-heading");
  heading.append(el("h2", "", "Deck checks and cut suggestions"));
  const pairLabel = el("label", "deck-pair-control", "Suggested color pair");
  const pairSelect = el("select", "sealed-analysis-limit");
  pairSelect.setAttribute("aria-label", "Suggested color pair");
  for (const build of builds) {
    const option = el("option", "", `${build.name} · ${build.eligibleCount} eligible`);
    option.value = pairKey(build);
    pairSelect.append(option);
  }
  pairSelect.value = pairKey(selected);
  pairSelect.addEventListener("change", () => {
    selectedDeckPair = pairSelect.value;
    render(currentState);
  });
  pairLabel.append(pairSelect);
  heading.append(pairLabel);
  section.append(heading);

  const note = `Rating-led starting point: the top ${selected.cards.length} of ${selected.eligibleCount} nonland cards that fit ${selected.name}. This is a heuristic, not a finished deck recommendation.`;
  section.append(el("p", "deck-analysis-note", note));

  const checks = el("div", "deck-checks");
  for (const check of selected.balance.checks) {
    const item = el("article", "deck-check " + check.status);
    item.append(el("span", "deck-check-value", check.value),
      el("strong", "", check.label),
      el("span", "deck-check-detail", check.detail));
    checks.append(item);
  }
  section.append(checks);

  const metrics = el("div", "deck-metrics");
  const curve = el("div", "deck-curve");
  curve.append(el("h3", "", `Mana curve · ${selected.balance.knownManaCosts}/${selected.cards.length} costs known`));
  const maxCurve = Math.max(1, ...selected.balance.curve.map((item) => item.count));
  for (const item of selected.balance.curve) {
    const row = el("div", "deck-curve-row");
    row.append(el("span", "", String(item.manaValue)));
    const track = el("span", "deck-curve-track");
    const bar = el("span", "deck-curve-bar");
    bar.style.width = `${item.count / maxCurve * 100}%`;
    track.append(bar);
    row.append(track, el("b", "", String(item.count)));
    curve.append(row);
  }
  if (!selected.balance.curve.length) curve.append(el("span", "deck-check-detail", "Mana costs unavailable."));
  metrics.append(curve);
  const colors = el("div", "deck-color-pips");
  colors.append(el("h3", "", "Colored mana requirements"));
  const pips = Object.entries(selected.balance.pips);
  colors.append(el("p", "", pips.length
    ? pips.map(([color, count]) => `${color}: ${count}`).join(" · ")
    : "No colored mana costs available."));
  if (selected.averageScore !== null) {
    colors.append(el("p", "", `Average available grade: ${selected.averageScore}`));
  }
  metrics.append(colors);
  section.append(metrics);

  const suggestions = el("section", "deck-suggestions");
  suggestions.append(el("h3", "", `Suggested spells (${selected.cards.length})`));
  const suggestedCards = el("div", "deck-suggested-cards");
  for (const card of selected.cards) suggestedCards.append(renderPoolCard(card));
  suggestions.append(suggestedCards);
  section.append(suggestions);

  const cuts = el("section", "deck-cuts");
  cuts.append(el("h3", "", "Potential cuts"));
  if (!selected.cuts.length) {
    cuts.append(el("p", "deck-check-detail", "No cards left outside this suggested build."));
  } else {
    const cutCards = el("div", "deck-cut-cards");
    for (const card of selected.cuts) {
      const item = el("div", "deck-cut-card");
      item.append(el("span", "deck-cut-reason", card.cutReason), renderPoolCard(card));
      cutCards.append(item);
    }
    cuts.append(cutCards);
  }
  section.append(cuts);
  container.append(section);
}

function renderDraftReplay(container, draft) {
  const observations = draft.observations || [];
  if (!observations.length) {
    container.append(el("h2", "", `Draft replay · ${draft.event || "Unknown event"}`));
    container.append(el("div", "empty", "No pack observations were saved for this draft."));
    return;
  }
  const pickedCards = observations.flatMap((observation) => observation.chosenCards || []);
  renderDeckAnalysis(container, draft.deckBuild);
  const colorGroups = [
    ["W", "White"], ["U", "Blue"], ["B", "Black"], ["R", "Red"], ["G", "Green"],
    ["Multicolor", "Multicolor"], ["Colorless", "Colorless"],
  ];
  const pickSummary = el("section", "history-draft-picks");
  pickSummary.append(el("h2", "", `Your draft picks · ${pickedCards.length} cards`));
  for (const [key, label] of colorGroups) {
    const cardsInColor = pickedCards
      .filter((card) => sealedColorGroup(card) === key)
      .sort((a, b) => a.name.localeCompare(b.name));
    if (!cardsInColor.length) continue;
    const group = el("section", "history-pick-color");
    group.tabIndex = 0;
    group.setAttribute("aria-label", `${label} draft picks; hover or focus to expand`);
    group.append(el("h3", "", `${label} · ${cardsInColor.length} cards`));
    const stack = el("div", "history-pick-stack");
    for (const card of cardsInColor) stack.append(renderCard({ ...card, chosen: true }, false));
    group.append(stack);
    pickSummary.append(group);
  }
  if (!pickedCards.length) {
    pickSummary.append(el("div", "empty", "No selected cards could be inferred from this draft log."));
  }
  container.append(pickSummary);
  container.append(el("h2", "", `Draft replay · ${draft.event || "Unknown event"}`));
  replayIndex = Math.max(0, Math.min(replayIndex, observations.length - 1));
  const observation = observations[replayIndex];
  const controls = el("div", "history-controls");
  const previous = el("button", "", "Previous pick");
  previous.type = "button";
  previous.disabled = replayIndex === 0;
  previous.addEventListener("click", () => {
    replayIndex--;
    render(currentState);
  });
  const next = el("button", "", "Next pick");
  next.type = "button";
  next.disabled = replayIndex >= observations.length - 1;
  next.addEventListener("click", () => {
    replayIndex++;
    render(currentState);
  });
  const pack = observation.pack === null ? "?" : observation.pack + 1;
  const pick = observation.pick === null ? "?" : observation.pick + 1;
  controls.append(previous, el("b", "", `Pick ${replayIndex + 1} of ${observations.length} · Pack ${pack}, pick ${pick}`), next);
  container.append(controls);
  if ((observation.chosenCards || []).length) {
    container.append(el("div", "history-picked",
      `Your pick: ${observation.chosenCards.map((card) => card.name).join(", ")}`,
    ));
  }
  const cards = el("div", "history-pack-cards");
  for (const card of observation.cards || []) {
    cards.append(renderCard({
      ...card,
      chosen: (observation.chosenIds || []).includes(card.arenaId),
    }, false));
  }
  for (const card of observation.takenCards || []) {
    cards.append(renderCard({ ...card, takenByOthers: true }, false));
  }
  container.append(cards);
}

function renderSealedHistory(container, sealed) {
  container.append(
    el("h2", "", `Sealed history · ${sealed.event || "Unknown event"}`),
    el("p", "", `${sealed.cardCount} cards saved · ${historyDate(sealed.createdAt)}`),
  );
  const cards = el("div", "history-pack-cards");
  for (const card of sealed.cards || []) cards.append(renderPoolCard(card));
  container.append(cards);
}

async function loadHistoryEntry(kind, id) {
  const selection = { kind, id };
  historySelection = selection;
  historyDetail = null;
  historyLoading = true;
  historyError = null;
  replayIndex = 0;
  selectedDeckPair = null;
  render(currentState);
  try {
    const response = await fetch(`/api/history/${kind}/${encodeURIComponent(id)}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`History request failed (${response.status})`);
    const detail = await response.json();
    if (historySelection?.kind === kind && historySelection.id === id) historyDetail = detail;
  } catch (error) {
    if (historySelection?.kind === kind && historySelection.id === id) {
      historyError = error.message || "Could not load saved history.";
    }
  } finally {
    if (historySelection?.kind === selection.kind && historySelection.id === selection.id) {
      historyLoading = false;
      if (currentState) render(currentState);
    }
  }
}

function updateRatingSourceControl(state) {
  const wrapper = document.getElementById("rating-source-control");
  const select = document.getElementById("rating-source");
  const sources = [...new Set((state.cards || []).flatMap((card) =>
    (card.ratings || []).filter((rating) => typeof rating.score === "number").map((rating) => rating.source),
  ))].sort((a, b) => a.localeCompare(b));
  if (!sources.includes(selectedRatingSource)) selectedRatingSource = AGGREGATE_RATING;
  wrapper.hidden = !state.pack || Boolean(state.game) || activeView !== "draft" || !sources.length;
  select.replaceChildren();
  for (const [value, text] of [[AGGREGATE_RATING, "Aggregated"], ...sources.map((source) => [source, source])]) {
    const option = el("option", "", text);
    option.value = value;
    select.append(option);
  }
  select.value = selectedRatingSource;
}

function cardsForRatingSource(cards) {
  if (selectedRatingSource === AGGREGATE_RATING) return cards;
  const displayCards = cards.map((card) => {
    const rating = (card.ratings || []).find((item) =>
      item.source === selectedRatingSource && typeof item.score === "number",
    );
    if (!rating) {
      return {
        ...card,
        score: null,
        grade: null,
        rank: null,
        rankOf: null,
        unrated: true,
        unratedMessage: `No ${selectedRatingSource} rating`,
        sourceRank: true,
      };
    }
    return {
      ...card,
      score: rating.score,
      grade: rating.grade,
      rank: null,
      rankOf: null,
      unrated: false,
      sourceRank: true,
    };
  });
  const ranked = displayCards
    .filter((card) => !card.unrated && card.score !== null)
    .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));
  const ranks = new Map(ranked.map((card, index) => [card, index + 1]));
  for (const card of displayCards) {
    card.rank = ranks.get(card) || null;
    card.rankOf = ranked.length;
  }
  return displayCards.sort((a, b) =>
    Number(a.unrated) - Number(b.unrated)
      || (b.score ?? -1) - (a.score ?? -1)
      || a.name.localeCompare(b.name),
  );
}

function renderStatus(state, error) {
  const s = document.getElementById("status");
  const parts = [];
  if (error) parts.push("server unreachable");
  else {
    if (state.status.demo) parts.push("DEMO");
    if (!state.status.cardDb) parts.push("Arena card DB not found");
    if (!state.status.logFound) parts.push("Player.log missing");
    if (state.status.updatedAt) parts.push("updated " + new Date(state.status.updatedAt * 1000).toLocaleTimeString());
    const a = document.getElementById("attr");
    if (state.status.attribution) a.href = state.status.attribution;
    if (state.status.source) a.textContent = state.status.source;
    document.getElementById("title").textContent = (state.set ? state.set + " " : "") + "draft guide";
    document.title = (state.set ? state.set + " " : "") + "Draft Guide";
  }
  s.textContent = parts.join(" · ");
  s.className = error || !state.status.cardDb || !state.status.logFound ? "warn" : "";
}

async function tick() {
  try {
    const res = await fetch("/api/state", { cache: "no-store" });
    const state = await res.json();
    renderStatus(state, false);
    if (state.version !== lastVersion) {
      lastVersion = state.version;
      render(state);
    }
  } catch (e) {
    renderStatus(null, true);
  }
}

tick();
setInterval(tick, POLL_MS);

document.getElementById("archetypes-toggle").addEventListener("click", () => {
  const panel = document.getElementById("archetypes");
  setArchetypesOpen(panel.hidden);
});

document.getElementById("rating-source").addEventListener("change", (event) => {
  selectedRatingSource = event.target.value;
  if (currentState) render(currentState);
});

document.getElementById("draft-tabs").addEventListener("click", (event) => {
  const button = event.target.closest("[data-view]");
  if (!button || !currentState) return;
  activeView = button.dataset.view;
  document.querySelectorAll("#draft-tabs [role=tab]").forEach((tab) => {
    tab.setAttribute("aria-selected", String(tab === button));
  });
  render(currentState);
});
