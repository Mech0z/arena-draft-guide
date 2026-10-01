"use strict";
const POLL_MS = 1000;
let lastVersion = null;
let currentState = null;
let activeView = "draft";
let expandedSealedPair = null;

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
  const root = el("article", "card" + (isBest ? " best" : "") + (card.unrated ? " unrated" : ""));
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
  const title = el("div", "title");
  title.append(el("div", "name", card.name));
  title.append(el("div", "sub", card.unrated ? "No rating found" :
    (card.score === null ? "Not enough data" : `#${card.rank} of ${card.rankOf}`) + (card.rarity ? " \u00b7 " + card.rarity : "")));
  if (card.manaArena) title.querySelector(".sub").append(" ", manaEl(card.manaArena));
  head.append(title);
  body.append(head);

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
    document.createTextNode(` · ${ins.untapped} of ${ins.lands} lands untapped · colours ${ins.colours || "unknown"}`));
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
  add(ins.possible, "");
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
  if (!selectedArchetype) expandedSealedPair = null;

  const overview = el("section", "sealed-overview");
  overview.append(el("div", "sealed-legend",
    `Pool fit is heuristic: bomb ≥${pool.scoreThresholds.bomb}, strong ≥${pool.scoreThresholds.strong}, playable ≥${pool.scoreThresholds.playable}; archetype tiers come from the set guide.`));
  if (pool.archetypes && pool.archetypes.length) {
    const analysis = el("div", "sealed-analysis-grid");
    for (const archetype of pool.archetypes) {
      const card = el("article", "sealed-analysis");
      const selected = sealedArchetypeKey(archetype) === expandedSealedPair;
      if (selected) card.classList.add("selected");
      const top = el("div", "sealed-analysis-head");
      top.append(manaEl(archetype.colors.map((color) => "o" + color).join("")),
        el("strong", "", archetype.name),
        el("span", "archetype-tier " + archetypeTierClass(archetype.tier), archetype.tier ? "Tier " + archetype.tier : "No tier"));
      const expand = el("button", "sealed-expand", selected ? "Show full pool" : "Show eligible cards");
      expand.type = "button";
      expand.setAttribute("aria-pressed", String(selected));
      expand.addEventListener("click", () => {
        expandedSealedPair = selected ? null : sealedArchetypeKey(archetype);
        render(currentState);
      });
      card.append(top, el("div", "sealed-potential potential-" + archetype.potentialRank, archetype.potential));
      const stats = el("div", "sealed-fit-stats");
      stats.append(el("span", "", `${archetype.bombs} bombs`),
        el("span", "", `${archetype.strong} strong`),
        el("span", "", `${archetype.playables} playables`),
        el("span", "", `${archetype.eligibleCards} eligible`));
      if (archetype.top23Average !== null) {
        stats.append(el("span", "", `top-card avg ${archetype.top23Average}`));
      }
      card.append(stats, expand);
      analysis.append(card);
    }
    overview.append(analysis);
  }
  cards.append(overview);

  const selectedCards = selectedArchetype
    ? pool.cards.filter((card) => isEligiblePoolCard(card, selectedArchetype))
    : pool.cards;
  const poolHeading = el("div", "sealed-pool-heading");
  poolHeading.append(el("h2", "", selectedArchetype
    ? `Eligible cards · ${selectedArchetype.name}`
    : "Full sealed pool"));
  if (selectedArchetype) {
    const restore = el("button", "sealed-expand", "Show full pool");
    restore.type = "button";
    restore.addEventListener("click", () => {
      expandedSealedPair = null;
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
  for (const key of order) {
    const group = grouped.get(key);
    if (!group.length) continue;
    group.sort((a, b) => (b.score ?? -1) - (a.score ?? -1) || a.name.localeCompare(b.name));
    const section = el("section", "sealed-color-group");
    section.append(el("h2", "", `${labels[key]} · ${group.reduce((sum, card) => sum + card.count, 0)} cards`));
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
  if (!state.sealedPool) expandedSealedPair = null;
  if (state.sealedPool && !previousState?.sealedPool && !state.game && !state.pack) activeView = "sealed";
  if (!state.sealedPool && activeView === "sealed") activeView = state.game ? "library" : "draft";
  if (state.game && activeView === "draft") activeView = "library";
  if (!state.game && activeView === "library") activeView = state.sealedPool ? "sealed" : "draft";
  preview.hide();
  renderArchetypes(state.archetypes, Boolean(state.game));
  const tabs = document.getElementById("draft-tabs");
  const draftTab = tabs.querySelector('[data-view="draft"]');
  const tiersTab = tabs.querySelector('[data-view="tiers"]');
  const sealedTab = tabs.querySelector('[data-view="sealed"]');
  const libraryTab = tabs.querySelector('[data-view="library"]');
  const hasTiers = Boolean(state.archetypes && state.archetypes.archetypes.length);
  draftTab.hidden = Boolean(state.game);
  tiersTab.hidden = !hasTiers;
  sealedTab.hidden = !state.sealedPool;
  libraryTab.hidden = !state.game;
  tabs.hidden = !state.sealedPool && (Boolean(state.game) || !hasTiers);
  tabs.querySelectorAll("[role=tab]").forEach((tab) => {
    tab.setAttribute("aria-selected", String(tab.dataset.view === activeView));
  });
  if (!state.game) renderInstants(null);
  if (activeView === "sealed" && state.sealedPool) return renderSealedPool(state.sealedPool);
  if (activeView === "tiers" && state.archetypes) return renderColorTiers(state.archetypes);
  if (state.game) return renderLibrary(state);
  document.getElementById("cards").className = "";
  const cards = document.getElementById("cards");
  cards.replaceChildren();
  const info = document.getElementById("pickinfo");
  const p = state.pack;
  info.textContent = p ? [p.event, p.pack && `Pack ${p.pack}`, p.pick && `Pick ${p.pick}`, `${state.cards.length} cards`].filter(Boolean).join(" · ") : "";
  if (!state.cards.length) {
    cards.append(el("div", "empty", state.status.logFound
      ? state.sealedPool
        ? "No draft pack is active. This is a sealed pool, not a draft; use the Sealed pool tab to view it."
        : "Waiting for a draft pack… open a pack in Arena and it will appear here."
      : "Arena Player.log not found."));
    return;
  }
  const bestScore = Math.max(...state.cards.map((c) => (c.unrated ? -1 : c.score ?? -1)));
  state.cards.forEach((card) => cards.append(renderCard(card, !card.unrated && card.score === bestScore)));
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

document.getElementById("draft-tabs").addEventListener("click", (event) => {
  const button = event.target.closest("[data-view]");
  if (!button || !currentState) return;
  activeView = button.dataset.view;
  document.querySelectorAll("#draft-tabs [role=tab]").forEach((tab) => {
    tab.setAttribute("aria-selected", String(tab === button));
  });
  render(currentState);
});
