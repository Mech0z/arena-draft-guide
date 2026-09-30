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
  if (card.image) {
    const img = el("img");
    img.src = card.image;
    img.alt = card.name;
    root.append(img);
  }
  const body = el("div", "body");
  const head = el("div", "head");
  if (!card.unrated) {
    const score = el("div", "score", card.score === null ? "–" : Math.round(card.score));
    if (card.score !== null) score.style.background = scoreColor(card.score);
    head.append(score);
  }
  const title = el("div", "title");
  title.append(el("div", "name", card.name));
  title.append(el("div", "sub", card.unrated ? "No rating found" :
    `#${card.rank} of ${card.rankOf} · ${[card.manaCost, card.rarity].filter(Boolean).join(" · ")}`));
  head.append(title);
  body.append(head);

  const texts = el("div", "texts");
  for (const r of card.ratings || []) {
    if (!r.comment) continue;
    const p = el("p", "");
    p.append(el("b", "", r.source + ": "), document.createTextNode(r.comment));
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
