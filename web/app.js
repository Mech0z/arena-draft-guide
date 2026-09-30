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

function renderLibrary(state) {
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
      row.append(el("span", "cnt", c.count + "×"), el("span", "lname", c.name), el("span", "chance", pct(c.chance)));
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
  preview.hide();
  if (state.game) return renderLibrary(state);
  document.getElementById("cards").className = "";
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

