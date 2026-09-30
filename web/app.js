"use strict";
const POLL_MS = 1000;
let lastVersion = null;

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
  const top = el("div", "top");
  if (card.image) {
    const img = el("img");
    img.src = card.image;
    img.alt = card.name;
    img.loading = "lazy";
    top.append(img);
  }
  const meta = el("div", "meta");
  meta.append(el("div", "name", card.name));
  meta.append(el("div", "sub", [card.manaCost, card.typeLine, card.rarity].filter(Boolean).join(" · ")));
  if (card.unrated) {
    meta.append(el("div", "rank", "No rating found"));
  } else {
    const score = el("div", "score", card.score === null ? "–" : Math.round(card.score));
    if (card.score !== null) score.style.background = scoreColor(card.score);
    meta.append(score);
    meta.append(el("div", "rank", `#${card.rank} of ${card.rankOf} overall · #${card.colorRank} of ${card.colorRankOf} in color`));
    if (card.signal && card.signal !== "consensus") meta.append(el("div", "rank", `Reviewers: ${card.signal}`));
  }
  top.append(meta);
  root.append(top);
  for (const r of card.ratings || []) {
    const row = el("div", "rating-row");
    row.append(el("span", "src", r.source), el("span", "g", String(r.grade)), el("span", "", String(Math.round(r.score))));
    root.append(row);
  }
  for (const r of card.ratings || []) {
    if (!r.comment) continue;
    const c = el("div", "comment");
    c.append(el("b", "", r.source + ": "), document.createTextNode(r.comment));
    root.append(c);
  }
  if (card.notes && card.notes.length) {
    const notes = el("div", "notes");
    for (const n of card.notes) {
      const p = el("div", "");
      p.append(el("b", "", n.source + ": "), document.createTextNode(n.text));
      notes.append(p);
    }
    root.append(notes);
  }
  return root;
}

function render(state) {
  const cards = document.getElementById("cards");
  cards.replaceChildren();
  const info = document.getElementById("pickinfo");
  const p = state.pack;
  info.textContent = p ? [p.event, p.pack && `Pack ${p.pack}`, p.pick && `Pick ${p.pick}`, `${state.cards.length} cards`].filter(Boolean).join(" · ") : "";
  if (!state.cards.length) {
    cards.append(el("div", "empty", state.status.logFound
      ? "Waiting for a draft pack… open a pack in Arena and it will appear here."
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
