/* Moteur du site (repris d'AmeliorIA et memoria-gcp) : construit les onglets, les menus latéraux et les pages à partir de SITE
   (www/data/content.js, produit par build/build.py) et des générateurs déclarés dans GENERATORS
   (www/generators/*.js). Tout le contenu est rendu une fois au chargement : la navigation ne fait
   qu'afficher ou masquer, et la recherche porte sur l'ensemble du site. */

/* ---------- Préférences persistées ---------- */
const store = {
  get(key){ try { return localStorage.getItem(key); } catch (e) { return null; } },
  set(key, value){ try { localStorage.setItem(key, value); } catch (e) {} },
};

const ZOOM_KEY = "exemplia-zoom", ZOOM_MIN = 0.7, ZOOM_MAX = 1.6, ZOOM_STEP = 0.1, ZOOM_BASE = 1.2;
let currentZoom = parseFloat(store.get(ZOOM_KEY)) || 1;
function applyZoom(z){
  currentZoom = Math.round(Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z)) * 100) / 100;
  document.documentElement.style.zoom = currentZoom * ZOOM_BASE;
  store.set(ZOOM_KEY, currentZoom);
  document.getElementById("zoom-level").textContent = Math.round(currentZoom * 100) + "%";
}
document.getElementById("zoom-out").addEventListener("click", () => applyZoom(currentZoom - ZOOM_STEP));
document.getElementById("zoom-in").addEventListener("click", () => applyZoom(currentZoom + ZOOM_STEP));
applyZoom(currentZoom);

const THEME_KEY = "exemplia-theme";
const themeToggleBtn = document.getElementById("theme-toggle");
function currentIsDark(){
  const explicit = document.documentElement.getAttribute("data-theme");
  if (explicit) return explicit === "dark";
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}
function syncThemeToggle(){
  themeToggleBtn.setAttribute("aria-pressed", String(currentIsDark()));
  themeToggleBtn.setAttribute("aria-label", currentIsDark() ? "Passer en mode clair" : "Passer en mode sombre");
}
themeToggleBtn.addEventListener("click", () => {
  const next = currentIsDark() ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  store.set(THEME_KEY, next);
  syncThemeToggle();
});
syncThemeToggle();

/* Icône : document à lignes, barre de défilement à droite (état visible) et pastille œil ou œil barré */
const ICON_SCROLLBAR_BASE = '<rect x="7" y="2" width="12" height="15" rx="2" fill="none" stroke="#7C88A6" stroke-width="1.4"/>'
  + '<line x1="9.5" y1="6" x2="15" y2="6" stroke="#B7C0D6" stroke-width="1.3" stroke-linecap="round"/>'
  + '<line x1="9.5" y1="9" x2="15" y2="9" stroke="#B7C0D6" stroke-width="1.3" stroke-linecap="round"/>'
  + '<line x1="9.5" y1="12" x2="13" y2="12" stroke="#B7C0D6" stroke-width="1.3" stroke-linecap="round"/>';
const ICON_SCROLLBAR_ON = '<svg viewBox="0 0 24 24">' + ICON_SCROLLBAR_BASE
  + '<rect x="16.2" y="4" width="1.8" height="7" rx="0.9" fill="var(--accent)"/>'
  + '<g transform="translate(-0.5,12) scale(0.55)" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
  + '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3" fill="var(--accent)" stroke="none"/></g></svg>';
const ICON_SCROLLBAR_OFF = '<svg viewBox="0 0 24 24">' + ICON_SCROLLBAR_BASE
  + '<g transform="translate(-0.5,12) scale(0.55)" fill="none" stroke="#3F4756" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
  + '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3" fill="#3F4756" stroke="none"/>'
  + '<line x1="1" y1="4" x2="23" y2="20"/></g></svg>';
const SCROLLBAR_KEY = "exemplia-sidebar-scrollbar";
const scrollbarToggleBtn = document.getElementById("scrollbar-toggle");
const sidebarScrollEl = document.getElementById("sidebar-scroll");
function applyScrollbarPref(visible){
  sidebarScrollEl.classList.toggle("scrollbar-visible", visible);
  scrollbarToggleBtn.innerHTML = visible ? ICON_SCROLLBAR_ON : ICON_SCROLLBAR_OFF;
  scrollbarToggleBtn.setAttribute("aria-pressed", String(visible));
  store.set(SCROLLBAR_KEY, visible ? "1" : "0");
}
scrollbarToggleBtn.addEventListener("click", () => applyScrollbarPref(!sidebarScrollEl.classList.contains("scrollbar-visible")));
applyScrollbarPref(store.get(SCROLLBAR_KEY) === "1");

/* Menu latéral masquable (classe sur <html>, posée dès le chargement par index.html) : bouton en bas du menu pour
   le masquer, icône en haut à gauche pour le réafficher, touche M pour basculer. */
const SIDEBAR_KEY = "exemplia-sidebar-cachee";
function applySidebarPref(cachee){
  document.documentElement.classList.toggle("sidebar-cachee", cachee);
  store.set(SIDEBAR_KEY, cachee ? "1" : "0");
}
document.getElementById("sidebar-toggle").addEventListener("click", () => applySidebarPref(true));
document.getElementById("sidebar-show").addEventListener("click", () => applySidebarPref(false));
document.addEventListener("keydown", e => {
  const cible = e.target;
  if (e.key.toLowerCase() !== "m" || e.ctrlKey || e.metaKey || e.altKey) return;
  if (cible.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(cible.tagName)) return;
  e.preventDefault();
  applySidebarPref(!document.documentElement.classList.contains("sidebar-cachee"));
});
applySidebarPref(store.get(SIDEBAR_KEY) === "1");

document.getElementById("last-updated").textContent = "Dernière mise à jour : " + SITE.updated;

/* ---------- Helpers ---------- */
function el(tag, className, text){
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function escapeHtml(str){
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// Bouton « Copier » sur chaque bloc de code d'un conteneur (contenu et sorties de générateurs)
function addCopyButtons(root){
  root.querySelectorAll("pre.block-code").forEach(pre => {
    if (pre.querySelector(".copy-btn")) return;
    const btn = el("button", "copy-btn", "Copier");
    btn.type = "button";
    btn.addEventListener("click", () => {
      const code = pre.querySelector("code") || pre;
      navigator.clipboard.writeText(code.textContent).then(() => {
        btn.textContent = "Copié";
        btn.classList.add("copied");
        setTimeout(() => { btn.textContent = "Copier"; btn.classList.remove("copied"); }, 1400);
      });
    });
    pre.appendChild(btn);
  });
}

// Défile #main-root jusqu'à un élément sans Element.scrollIntoView() : avec le zoom CSS de la page,
// scrollIntoView() décale aussi la fenêtre elle-même, ce qui sort durablement le menu du champ.
// getBoundingClientRect() est en coordonnées zoomées, scrollTop non : d'où la division par le zoom.
function scrollElementIntoMainRoot(target, opts){
  const mainRoot = document.getElementById("main-root");
  if (!target) return;
  const zoom = parseFloat(document.documentElement.style.zoom) || 1;
  const r = target.getBoundingClientRect();
  const root = mainRoot.getBoundingClientRect();
  const delta = ((opts && opts.center)
    ? (r.top + r.height / 2) - (root.top + root.height / 2)
    : r.top - root.top - 12) / zoom;
  mainRoot.scrollTo({top: mainRoot.scrollTop + delta, behavior: (opts && opts.smooth) ? "smooth" : "auto"});
}

/* ---------- Construction des onglets et des pages ---------- */
const PAGES = SITE.pages;
const topTabsEl = document.getElementById("top-tabs");
const mainRootEl = document.getElementById("main-root");
// Une page de section générée (<id>.html) porte une version statique de son contenu, pour les
// moteurs de recherche ; le moteur la remplace par le site complet.
mainRootEl.textContent = "";
const idToPage = {};
const firstIdForPage = {};
const lastIdForPage = {};

PAGES.forEach(page => {
  const tab = el("button", "top-tab", page.label);
  tab.type = "button";
  tab.dataset.page = page.key;
  tab.addEventListener("click", () => go(lastIdForPage[page.key] || firstIdForPage[page.key] || page.key));
  topTabsEl.appendChild(tab);

  const nav = el("div", "page-navbody");
  nav.id = "navbody-" + page.key;
  sidebarScrollEl.appendChild(nav);
  const main = el("div", "page-main");
  main.id = "mainpage-" + page.key;
  mainRootEl.appendChild(main);

  if (page.type === "lexique") buildLexiquePage(page, nav, main);
  else if (page.type === "generateurs") buildGeneratorsPage(page, nav, main);
  else buildSectionsPage(page, nav, main);
});

// Menu latéral de l'Accueil : les autres projets IA de tekio.org (site.yml, `projets`)
const navAccueil = document.getElementById("navbody-accueil");
if (navAccueil && SITE.projets.length){
  const projets = makeNavBox(navAccueil, "group", "Autres projets IA");
  projets.box.classList.remove("collapsed");
  SITE.projets.forEach(p => {
    const a = el("a", "nav-item nav-projet");
    a.href = p.url;
    a.target = "_blank";
    a.rel = "noopener";
    a.innerHTML = '<span class="nav-projet-nom">' + escapeHtml(p.nom) + ' ↗</span><span class="nav-projet-desc">' + escapeHtml(p.desc) + '</span>';
    projets.items.appendChild(a);
  });
}

// Boîte repliable du menu latéral, même composant pour un groupe et un sous-groupe
function makeNavBox(parent, kind, label, count){
  const box = el("div", "nav-" + kind + " collapsed");
  const labelEl = el("div", "nav-" + kind + "-label");
  labelEl.innerHTML = '<span class="label-text"></span>'
    + (count !== undefined ? '<span class="count">' + count + '</span>' : '')
    + '<span class="chevron">▾</span>';
  labelEl.querySelector(".label-text").textContent = label;
  labelEl.addEventListener("click", () => box.classList.toggle("collapsed"));
  const items = el("div", "nav-" + kind + "-items");
  box.append(labelEl, items);
  parent.appendChild(box);
  return {box, items};
}

function makeNavItem(parent, id, title, icon, deprecie){
  const btn = el("button", "nav-item" + (icon ? " with-icon" : "") + (deprecie ? " deprecated" : ""));
  btn.type = "button";
  if (icon){
    const img = el("img", "nav-icon");
    img.src = icon;
    img.alt = "";
    btn.appendChild(img);
  }
  btn.appendChild(el("span", "", title));
  btn.dataset.target = id;
  btn.addEventListener("click", () => go(id));
  parent.appendChild(btn);
}

function makePanel(main, id, title, icon, aka, deprecie){
  const panel = el("section", "panel");
  panel.id = "panel-" + id;
  const header = el("div", "panel-header" + (icon ? " with-icon" : "") + (deprecie ? " deprecated" : ""));
  if (icon){
    const img = el("img", "panel-icon");
    img.src = icon;
    img.alt = "";
    header.appendChild(img);
  }
  const titles = el("div", "panel-titles");
  titles.appendChild(el("h2", "", title));
  if (aka) titles.appendChild(el("div", "panel-aka", "Aussi appelé : " + aka));
  header.appendChild(titles);
  panel.appendChild(header);
  main.appendChild(panel);
  return panel;
}

// Regroupe le contenu d'une section en cadres : un cadre par titre de niveau 2 (et un pour ce qui
// précède le premier titre) ; les schémas, déjà encadrés, restent à part.
function groupIntoCards(body){
  let card = null;
  Array.from(body.childNodes).forEach(node => {
    if (node.nodeType === Node.TEXT_NODE && !node.textContent.trim()){ node.remove(); return; }
    if (node.nodeType === Node.ELEMENT_NODE && node.matches("figure.block-diagram, .deprecated-banner")){ card = null; return; }
    if (!card || (node.nodeType === Node.ELEMENT_NODE && node.tagName === "H2")){
      card = el("div", "md-card");
      body.insertBefore(card, node);
    }
    card.appendChild(node);
  });
}

function buildSectionsPage(page, nav, main){
  const sections = SITE.sections.filter(s => s.page === page.key);
  if (!sections.length){
    const empty = el("div", "page-empty");
    empty.innerHTML = '<div class="page-header"><h2></h2></div><p>Contenu à venir. Rubriques prévues :</p><ul></ul>';
    empty.querySelector("h2").textContent = page.label;
    Object.values(page.groups).forEach(label => empty.querySelector("ul").appendChild(el("li", "", label)));
    main.appendChild(empty);
  }
  Object.entries(page.groups).forEach(([groupKey, groupLabel]) => {
    const groupSections = sections.filter(s => s.group === groupKey);
    const group = makeNavBox(nav, "group", groupLabel, groupSections.length || undefined);
    if (!groupSections.length) group.box.classList.add("empty");
    let currentSub = null, subItems = null;
    groupSections.forEach(sec => {
      if (sec.subgroup && sec.subgroup !== currentSub){
        currentSub = sec.subgroup;
        subItems = makeNavBox(group.items, "subgroup", sec.subgroup).items;
      } else if (!sec.subgroup){
        currentSub = null;
        subItems = null;
      }
      makeNavItem(subItems || group.items, sec.id, sec.nav || sec.title, sec.icon, sec.deprecie);
      const panel = makePanel(main, sec.id, sec.title, sec.icon, sec.aka, sec.deprecie);
      const body = el("div", "md");
      body.innerHTML = sec.html;
      groupIntoCards(body);
      panel.appendChild(body);
      idToPage[sec.id] = page.key;
      if (!firstIdForPage[page.key]) firstIdForPage[page.key] = sec.id;
    });
  });
}

function buildLexiquePage(page, nav, main){
  const header = el("div", "page-header");
  header.appendChild(el("h2", "", page.label));
  main.appendChild(header);
  main.appendChild(el("p", "page-intro", "Termes et sigles, avec un renvoi vers la section qui les détaille."));
  const letters = el("div", "nav-letters");
  nav.appendChild(letters);
  let letterSection = null, currentLetter = null;
  SITE.lexique.forEach(entry => {
    const letter = entry.t.normalize("NFD").charAt(0).toUpperCase();
    if (letter !== currentLetter){
      currentLetter = letter;
      letterSection = el("section", "lex-letter");
      letterSection.id = "lex-" + letter.toLowerCase();
      letterSection.appendChild(el("h2", "lex-letter-heading", letter));
      main.appendChild(letterSection);
      const btn = el("button", "nav-letter", letter);
      btn.type = "button";
      const target = letterSection.id;
      btn.addEventListener("click", () => go(target));
      letters.appendChild(btn);
    }
    const entryEl = el("div", "lex-entry");
    entryEl.id = entry.id;
    entryEl.appendChild(el("div", "lex-term", entry.t));
    const def = el("div", "lex-def");
    def.innerHTML = entry.html;
    entryEl.appendChild(def);
    letterSection.appendChild(entryEl);
  });
}

function buildGeneratorsPage(page, nav, main){
  const group = makeNavBox(nav, "group", page.label);
  group.box.classList.remove("collapsed");
  GENERATORS.forEach(gen => {
    const id = "gen-" + gen.id;
    makeNavItem(group.items, id, gen.title);
    const panel = makePanel(main, id, gen.title);
    if (gen.intro) panel.appendChild(el("p", "page-intro", gen.intro));
    const body = el("div", "md");
    panel.appendChild(body);
    gen.render(body);
    idToPage[id] = page.key;
    if (!firstIdForPage[page.key]) firstIdForPage[page.key] = id;
  });
}

mainRootEl.querySelectorAll(".md table").forEach(table => {
  const wrap = el("div", "table-wrap");
  table.replaceWith(wrap);
  wrap.appendChild(table);
});
addCopyButtons(mainRootEl);

/* ---------- Navigation (hash) ---------- */
let currentPage = null;

function showPage(key){
  currentPage = key;
  document.querySelectorAll(".top-tab").forEach(t => t.classList.toggle("active", t.dataset.page === key));
  document.querySelectorAll(".page-navbody").forEach(n => n.classList.toggle("active", n.id === "navbody-" + key));
  document.querySelectorAll(".page-main").forEach(m => m.classList.toggle("active", m.id === "mainpage-" + key));
}

/* Schémas Mermaid : rendus à l'affichage de leur section (un schéma masqué se mesure mal) */
function renderMermaid(root){
  if (!window.mermaid || !root) return;
  const nodes = Array.from(root.querySelectorAll("pre.mermaid:not([data-processed])"));
  if (nodes.length) window.mermaid.run({nodes});
}
window.addEventListener("load", () => {
  if (!window.mermaid) return;
  window.mermaid.initialize({startOnLoad: false, theme: "neutral", securityLevel: "strict",
                             themeVariables: {fontSize: "15px"},
                             flowchart: {htmlLabels: true, useMaxWidth: false, nodeSpacing: 28}});
  renderMermaid(document.querySelector(".panel.active"));
});

function showSection(id){
  const page = idToPage[id];
  lastIdForPage[page] = id;
  if (page !== currentPage) showPage(page);
  const main = document.getElementById("mainpage-" + page);
  main.querySelectorAll(".panel").forEach(p => p.classList.toggle("active", p.id === "panel-" + id));
  document.querySelectorAll("#navbody-" + page + " .nav-item").forEach(b => {
    const active = b.dataset.target === id;
    b.classList.toggle("active", active);
    if (active){
      for (let box = b.closest(".nav-subgroup, .nav-group"); box; box = box.parentElement.closest(".nav-subgroup, .nav-group")){
        box.classList.remove("collapsed");
      }
    }
  });
  renderMermaid(document.getElementById("panel-" + id));
  mainRootEl.scrollTo(0, 0);
}

// Affiche la cible d'un hash : section, page, ou ancre interne (titre d'une section, terme du lexique)
function route(id){
  if (!id){
    const first = PAGES[0].key;
    return firstIdForPage[first] ? showSection(firstIdForPage[first]) : showPage(first);
  }
  if (idToPage[id]) return showSection(id);
  const page = PAGES.find(p => p.key === id);
  if (page){
    const sectionId = lastIdForPage[page.key] || firstIdForPage[page.key];
    return sectionId ? showSection(sectionId) : showPage(page.key);
  }
  const target = document.getElementById(id);
  if (!target) return route("");
  const panel = target.closest(".panel");
  if (panel) showSection(panel.id.slice("panel-".length));
  else showPage(target.closest(".page-main").id.slice("mainpage-".length));
  scrollElementIntoMainRoot(target);
  if (target.classList.contains("lex-entry")){
    target.classList.remove("flash");
    void target.offsetWidth;
    target.classList.add("flash");
  }
}

// pushState plutôt que location.hash = : l'affectation déclenche le défilement natif vers l'ancre,
// qui décale la fenêtre (cf. scrollElementIntoMainRoot).
function go(id){
  if (location.hash.slice(1) !== id) history.pushState(null, "", "#" + id);
  route(id);
}

document.addEventListener("click", e => {
  const a = e.target.closest('a[href^="#"]');
  if (!a || !a.getAttribute("href").slice(1)) return;
  e.preventDefault();
  go(decodeURIComponent(a.getAttribute("href").slice(1)));
});
// Sans hash, une page de section générée s'ouvre sur sa section (data-route sur <html>)
const defaultRoute = document.documentElement.dataset.route || "";
function hashRoute(){ return decodeURIComponent(location.hash.slice(1)) || defaultRoute; }
window.addEventListener("hashchange", () => route(hashRoute()));
route(hashRoute());

/* ---------- Recherche ---------- */
// Index construit au chargement à partir du contenu déjà rendu. Le texte est normalisé caractère
// par caractère (minuscules, sans accents) en gardant la même longueur que l'original, pour que
// les positions trouvées dans le texte normalisé servent directement à l'extrait et au surlignage.
const normCache = new Map();
function normChar(c){
  const code = c.charCodeAt(0);
  if (code < 128) return (code >= 65 && code <= 90) ? String.fromCharCode(code + 32) : c;
  let r = normCache.get(c);
  if (r === undefined){
    r = c.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
    r = r.length ? r[0] : " ";
    normCache.set(c, r);
  }
  return r;
}
function norm(s){
  let out = "";
  for (let i = 0; i < s.length; i++) out += normChar(s[i]);
  return out;
}

const pageLabel = Object.fromEntries(PAGES.map(p => [p.key, p.label]));
const searchIndex = [];
function indexEntry(id, page, title, textEl){
  const text = (textEl ? textEl.textContent : "").replace(/\s+/g, " ").trim();
  searchIndex.push({id, page, title, titleN: norm(title), text, textN: norm(text)});
}
document.querySelectorAll(".panel").forEach(panel => {
  const id = panel.id.slice("panel-".length);
  const aka = panel.querySelector(".panel-aka");
  const title = panel.querySelector(".panel-header h2").textContent;
  indexEntry(id, idToPage[id], aka ? title + " (" + aka.textContent.replace(/^Aussi appelé : /, "") + ")" : title, panel.querySelector(".md"));
});
SITE.lexique.forEach(entry => indexEntry(entry.id, "lexique", entry.t, document.getElementById(entry.id).querySelector(".lex-def")));

function queryTerms(q){
  return norm(q).split(/\s+/).filter(Boolean);
}

function countOccurrences(hay, term, max){
  let n = 0, pos = hay.indexOf(term);
  while (pos >= 0 && n < max){ n++; pos = hay.indexOf(term, pos + term.length); }
  return n;
}

function search(q){
  const terms = queryTerms(q);
  if (!terms.length) return [];
  const phrase = terms.join(" ");
  const results = [];
  searchIndex.forEach(entry => {
    let score = 0;
    for (const t of terms){
      const inTitle = entry.titleN.includes(t);
      const inText = countOccurrences(entry.textN, t, 5);
      if (!inTitle && !inText) return;
      score += (inTitle ? 10 : 0) + inText;
    }
    if (terms.length > 1 && (entry.titleN.includes(phrase) || entry.textN.includes(phrase))) score += 8;
    results.push({entry, score});
  });
  return results.sort((a, b) => b.score - a.score).slice(0, 40);
}

// Intervalles [début, fin) des occurrences des termes dans un texte normalisé, fusionnés
function matchRanges(textN, terms){
  const ranges = [];
  terms.forEach(t => {
    for (let pos = textN.indexOf(t); pos >= 0; pos = textN.indexOf(t, pos + t.length)) ranges.push([pos, pos + t.length]);
  });
  ranges.sort((a, b) => a[0] - b[0]);
  const merged = [];
  ranges.forEach(r => {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
    else merged.push(r.slice());
  });
  return merged;
}

function snippetHtml(entry, terms){
  const ranges = matchRanges(entry.textN, terms);
  if (!ranges.length) return escapeHtml(entry.text.slice(0, 140)) + (entry.text.length > 140 ? "…" : "");
  const start = Math.max(0, ranges[0][0] - 50);
  const end = Math.min(entry.text.length, ranges[0][0] + 130);
  let out = start > 0 ? "…" : "", cursor = start;
  ranges.filter(r => r[0] >= start && r[1] <= end).forEach(r => {
    out += escapeHtml(entry.text.slice(cursor, r[0])) + "<b>" + escapeHtml(entry.text.slice(r[0], r[1])) + "</b>";
    cursor = r[1];
  });
  return out + escapeHtml(entry.text.slice(cursor, end)) + (end < entry.text.length ? "…" : "");
}

let marks = [];
function clearMarks(){
  marks.forEach(m => {
    const parent = m.parentNode;
    if (!parent) return;
    parent.replaceChild(document.createTextNode(m.textContent), m);
    parent.normalize();
  });
  marks = [];
}

function highlightIn(root, terms){
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node){
      const p = node.parentElement;
      if (!node.nodeValue.trim() || !p || p.closest("svg, script, style, button")) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    }
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach(node => {
    const text = node.nodeValue;
    const ranges = matchRanges(norm(text), terms);
    if (!ranges.length) return;
    const frag = document.createDocumentFragment();
    let cursor = 0;
    ranges.forEach(([a, b]) => {
      if (a > cursor) frag.appendChild(document.createTextNode(text.slice(cursor, a)));
      const mark = el("mark", "search-mark", text.slice(a, b));
      frag.appendChild(mark);
      marks.push(mark);
      cursor = b;
    });
    if (cursor < text.length) frag.appendChild(document.createTextNode(text.slice(cursor)));
    node.parentNode.replaceChild(frag, node);
  });
}

const searchInput = document.getElementById("search-input");
const resultsEl = document.getElementById("search-results");
let currentResults = [], selected = 0, searchTimer = null;

function renderResults(){
  const q = searchInput.value.trim();
  if (!q){ resultsEl.hidden = true; return; }
  currentResults = search(q);
  selected = 0;
  const terms = queryTerms(q);
  resultsEl.innerHTML = "";
  if (!currentResults.length){
    resultsEl.appendChild(el("div", "sr-empty", "Aucun résultat."));
  }
  currentResults.forEach((r, i) => {
    const item = el("button", "sr-item" + (i === 0 ? " selected" : ""));
    item.type = "button";
    const head = el("div", "sr-head");
    head.append(el("span", "sr-page", pageLabel[r.entry.page]), el("span", "sr-title", r.entry.title));
    const snippet = el("div", "sr-snippet");
    snippet.innerHTML = snippetHtml(r.entry, terms);
    item.append(head, snippet);
    item.addEventListener("mousedown", e => e.preventDefault());
    item.addEventListener("click", () => openResult(i));
    resultsEl.appendChild(item);
  });
  resultsEl.hidden = false;
}

function selectResult(i){
  const items = resultsEl.querySelectorAll(".sr-item");
  if (!items.length) return;
  selected = (i + items.length) % items.length;
  items.forEach((it, k) => it.classList.toggle("selected", k === selected));
  items[selected].scrollIntoView({block: "nearest"});
}

function openResult(i){
  const r = currentResults[i];
  if (!r) return;
  clearMarks();
  go(r.entry.id);
  const target = r.entry.page === "lexique" ? document.getElementById(r.entry.id) : document.getElementById("panel-" + r.entry.id);
  highlightIn(target, queryTerms(searchInput.value));
  if (marks.length){
    marks[0].classList.add("current");
    scrollElementIntoMainRoot(marks[0], {center: true});
  }
  resultsEl.hidden = true;
  searchInput.blur();
}

searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(renderResults, 120);
});
searchInput.addEventListener("focus", () => { if (searchInput.value.trim()) renderResults(); });
searchInput.addEventListener("blur", () => { resultsEl.hidden = true; });
searchInput.addEventListener("keydown", e => {
  if (e.key === "ArrowDown"){ e.preventDefault(); selectResult(selected + 1); }
  else if (e.key === "ArrowUp"){ e.preventDefault(); selectResult(selected - 1); }
  else if (e.key === "Enter"){
    e.preventDefault();
    clearTimeout(searchTimer);
    if (resultsEl.hidden) renderResults();
    openResult(selected);
  } else if (e.key === "Escape"){
    searchInput.value = "";
    resultsEl.hidden = true;
    clearMarks();
    searchInput.blur();
  }
});
document.addEventListener("keydown", e => {
  if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)){
    e.preventDefault();
    searchInput.focus();
  }
});
