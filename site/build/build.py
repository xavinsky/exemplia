#!/usr/bin/env python3
"""Compile la documentation du dépôt en site statique : www/data/content.js, plus une page HTML par
section pour le référencement.

Le site (www/index.html) reste un fichier statique qui s'ouvre en file:// : les données sont
chargées par <script src>, sous la forme `const SITE = {...}`, et non par fetch.

Le texte n'est pas recopié dans le site : chaque page lit un fichier Markdown du dépôt.

  content/site.yml                        onglets, groupes du menu, modules d'exemple de chaque groupe
  content/<page>/<groupe>/<NN>-<slug>.md  une section écrite pour le site, ou un renvoi vers un
                                          fichier du dépôt (`source: doc/installation.md`) ; le texte
                                          propre au fichier s'ajoute alors après celui de la source
  content/lexique.md                      un terme par titre `## Terme`
  src/exemplia/<module>/README.md         page « Présentation » de chaque module listé dans site.yml
  src/exemplia/<module>/comment-ca-marche.md + fonctionnement.md
                                          page « Comment ça marche ? » : le texte affiché par l'application,
                                          puis le détail technique (les deux fichiers sont facultatifs)
  src/exemplia/<module>/utilisation.md    page « Comment utiliser ? », si elle existe
  src/exemplia/<module>/evaluation.md     page « Évaluation », si elle existe
                                          (toutes les pages d'un module s'ouvrent sur le lien du répertoire
                                          du module sur GitHub)

Front matter d'une section : title (obligatoire), id (à défaut le slug du nom de fichier), nav
(libellé du menu), subgroup, description (référencement ; à défaut, le premier paragraphe), source.

Réécriture des liens d'un fichier du dépôt : un lien vers un autre fichier Markdown publié devient
un lien interne (#id, ou #id--titre pour une ancre) ; un lien vers un autre fichier du dépôt mène
à ce fichier sur GitHub. Les images sont copiées dans www/media/ ; un paragraphe réduit à une image
devient une capture cliquable. Les blocs ```mermaid sont dessinés dans le navigateur.

Syntaxe propre au site : encarts `> [!TIP]` / `> [!WARNING]` (alertes GitHub).

Usage : python3 site/build/build.py
"""

import datetime
import html
import json
import posixpath
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

import yaml
from markdown_it import MarkdownIt
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

ROOT = Path(__file__).resolve().parent.parent
DEPOT = ROOT.parent
MODULES = DEPOT / "src" / "exemplia"
CONTENT = ROOT / "content"
WWW = ROOT / "www"
OUTPUT = WWW / "data" / "content.js"
MEDIA = WWW / "media"
SITE_URL = "https://tekio.org/exemplia/"
GITHUB = "https://github.com/xavinsky/exemplia"
SITE_NAME = "Exemplia"
GENERATED_MARK = '<meta name="generator" content="exemplia site/build/build.py">'
SEO_BLOCK_RE = re.compile(r"<!-- seo -->.*?<!-- /seo -->", re.S)
RESERVED_PAGES = {"index", "engine", "style", "sitemap"}
DESCRIPTION_MAX = 160
CALLOUTS = {"NOTE": "tip", "TIP": "tip", "IMPORTANT": "tip", "WARNING": "warning", "CAUTION": "warning"}
FORMATTER = HtmlFormatter(nowrap=True, classprefix="tok-")
# Pages d'un module après la Présentation : (suffixe d'id, libellé du menu, fichiers concaténés).
PAGES_MODULE = (
    ("fonctionnement", "Comment ça marche ?", ("comment-ca-marche.md", "fonctionnement.md")),
    ("utilisation", "Comment utiliser ?", ("utilisation.md",)),
    ("evaluation", "Évaluation", ("evaluation.md",)),
)


class BuildError(Exception):
    pass


def slugify(text):
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def split_front_matter(text, path):
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        raise BuildError(f"{path}: front matter non fermé")
    meta = yaml.safe_load(text[4:end]) or {}
    return meta, text[end + 5:]


def split_title(text):
    """(titre de premier niveau, reste) d'un fichier Markdown du dépôt."""
    m = re.match(r"\s*# +(.+?)\s*\n", text)
    return (m.group(1), text[m.end():]) if m else (None, text)


def depot_path(path):
    """Chemin d'un fichier relatif à la racine du dépôt, en notation POSIX."""
    return path.resolve().relative_to(DEPOT).as_posix()


def highlight_code(code, lang, _attrs):
    lang = (lang or "").strip()
    if lang == "mermaid":
        # Schéma rendu dans le navigateur par Mermaid (www/engine.js), sur fond clair dans les deux thèmes
        return f'<pre class="mermaid">{html.escape(code)}</pre>\n'
    try:
        body = highlight(code, get_lexer_by_name(lang), FORMATTER) if lang else html.escape(code)
    except ClassNotFound:
        body = html.escape(code)
    cls = f' class="language-{lang}"' if lang else ""
    return f'<pre class="block-code"><code{cls}>{body}</code></pre>\n'


def make_parser():
    md = MarkdownIt("commonmark", {"html": True, "highlight": highlight_code})
    md.enable(["table", "strikethrough"])
    return md


class Renderer:
    """Rend un fichier Markdown en HTML, réécrit ses liens et images, relève ses liens internes."""

    def __init__(self, published):
        self.md = make_parser()
        self.published = published  # chemin dans le dépôt d'un fichier Markdown -> id de section
        self.links = []             # (fichier source, cible #id)
        self.media = set()

    def render(self, text, source, section_id=None):
        tokens = self.md.parse(text)
        anchors = []
        self._callouts(tokens)
        self._tables(tokens)
        if section_id:
            anchors = self._headings(tokens, section_id)
        self._images(tokens, source)
        self._links(tokens, source)
        tokens = self._captures(tokens)
        return self.md.renderer.render(tokens, self.md.options, {}), anchors

    @staticmethod
    def _callouts(tokens):
        # > [!WARNING] ... → encart coloré (syntaxe des alertes GitHub)
        for i, tok in enumerate(tokens):
            if tok.type != "blockquote_open" or i + 2 >= len(tokens):
                continue
            inline = tokens[i + 2]
            if inline.type != "inline" or not inline.children:
                continue
            first = inline.children[0]
            m = re.match(r"\[!(\w+)\]\s*", first.content) if first.type == "text" else None
            if not m or m.group(1).upper() not in CALLOUTS:
                continue
            tok.attrSet("class", "block-note " + CALLOUTS[m.group(1).upper()])
            first.content = first.content[m.end():]
            if not first.content and len(inline.children) > 1 and inline.children[1].type == "softbreak":
                del inline.children[:2]

    @staticmethod
    def _tables(tokens):
        for tok in tokens:
            if tok.type == "table_open":
                tok.attrSet("class", "md-table")

    @staticmethod
    def _headings(tokens, section_id):
        anchors = []
        for i, tok in enumerate(tokens):
            if tok.type == "heading_open":
                anchor = f"{section_id}--{slugify(tokens[i + 1].content)}"
                tok.attrSet("id", anchor)
                anchors.append(anchor)
        return anchors

    def _images(self, tokens, source):
        # Image d'un fichier du dépôt → copie dans www/media/<chemin dans le dépôt>
        for tok in tokens:
            for child in tok.children or []:
                if child.type != "image":
                    continue
                src = child.attrGet("src") or ""
                if re.match(r"https?://", src):
                    continue
                path = (source.parent / src).resolve()
                if not path.is_file():
                    raise BuildError(f"{source}: image introuvable {src}")
                rel = depot_path(path)
                self.media.add(rel)
                child.attrSet("src", f"media/{rel}")
                child.attrSet("loading", "lazy")

    def _links(self, tokens, source):
        for tok in tokens:
            for child in tok.children or []:
                if child.type != "link_open":
                    continue
                href = child.attrGet("href") or ""
                if re.match(r"https?://|mailto:", href):
                    child.attrSet("target", "_blank")
                    child.attrSet("rel", "noopener")
                    continue
                if href.startswith("#"):
                    self.links.append((source, href[1:]))
                    continue
                target, _, fragment = href.partition("#")
                path = (source.parent / target).resolve()
                try:
                    rel = depot_path(path)
                except ValueError:
                    raise BuildError(f"{source}: lien hors du dépôt {href}") from None
                if rel in self.published:
                    anchor = self.published[rel] + (f"--{slugify(fragment)}" if fragment else "")
                    child.attrSet("href", f"#{anchor}")
                    self.links.append((source, anchor))
                elif path.exists():
                    kind = "tree" if path.is_dir() else "blob"
                    child.attrSet("href", f"{GITHUB}/{kind}/main/{rel}" + (f"#{fragment}" if fragment else ""))
                    child.attrSet("target", "_blank")
                    child.attrSet("rel", "noopener")
                else:
                    raise BuildError(f"{source}: lien vers un fichier introuvable {href}")

    @staticmethod
    def _captures(tokens):
        # Paragraphe réduit à une image → capture cliquable, légende = texte alternatif
        out, i = [], 0
        while i < len(tokens):
            tok = tokens[i]
            children = tokens[i + 1].children if tok.type == "paragraph_open" else None
            if children and len(children) == 1 and children[0].type == "image":
                img = children[0]
                src, alt = img.attrGet("src"), html.escape(img.content)
                figure = tokens[i + 1].__class__("html_block", "", 0)
                figure.content = (
                    f'<figure class="capture large"><a href="{src}" target="_blank" rel="noopener">'
                    f'<img src="{src}" alt="{alt}" loading="lazy"></a>'
                    f"<figcaption>{alt}</figcaption></figure>\n")
                out.append(figure)
                i += 3
                continue
            out.append(tok)
            i += 1
        return out


def load_site():
    site = yaml.safe_load((CONTENT / "site.yml").read_text(encoding="utf-8"))
    for page in site["pages"]:
        page.setdefault("type", "sections")
        page.setdefault("groups", {})
        page.setdefault("modules", {})
    return site


def module_id(module):
    return module.replace("_", "-")


def module_entries(module):
    """(chemin, front matter, corps) des pages d'un module : Présentation, puis chacune des PAGES_MODULE
    dont au moins un fichier existe."""
    readme = MODULES / module / "README.md"
    if not readme.is_file():
        raise BuildError(f"site.yml : module sans README {readme.relative_to(DEPOT)}")
    title, body = split_title(readme.read_text(encoding="utf-8"))
    ident = module_id(module)
    dossier = f"src/exemplia/{module}/"
    code = (f'<p class="code-source">Code de l\'exemple : <a href="{GITHUB}/tree/main/{dossier}" target="_blank" '
            f'rel="noopener"><code>{dossier}</code></a> sur GitHub</p>\n\n')
    entries = [(readme, {"title": title, "nav": "Présentation", "id": ident, "subgroup": title}, code + body)]
    for suffixe, libelle, noms in PAGES_MODULE:
        fichiers = [MODULES / module / nom for nom in noms if (MODULES / module / nom).is_file()]
        if not fichiers:
            continue
        corps = "\n\n".join(split_title(f.read_text(encoding="utf-8"))[1].strip() for f in fichiers) + "\n"
        entries.append((fichiers[0], {"title": f"{libelle} {title}", "nav": libelle,
                                      "id": f"{ident}-{suffixe}", "subgroup": title,
                                      "description": f"{title} : {libelle.rstrip(' ?').lower()} de l'exemple Exemplia."},
                        code + corps))
    return entries


def content_entries(site):
    """Toutes les entrées, dans l'ordre du menu : (page, groupe, chemin, front matter, corps)."""
    out = []
    for page in site["pages"]:
        if page["type"] != "sections":
            continue
        page_dir = CONTENT / page["key"]
        unknown = {p.name for p in page_dir.glob("*/") if p.is_dir()} - set(page["groups"])
        if unknown:
            raise BuildError(f"{page_dir}: dossiers absents de site.yml : {sorted(unknown)}")
        for group in page["groups"]:
            for path in sorted((page_dir / group).glob("*.md")):
                meta, body = split_front_matter(path.read_text(encoding="utf-8"), path)
                meta.setdefault("id", re.sub(r"^\d+-", "", path.stem))
                if meta.get("source"):
                    source = DEPOT / meta["source"]
                    if not source.is_file():
                        raise BuildError(f"{path}: source introuvable {meta['source']}")
                    titre, texte = split_title(source.read_text(encoding="utf-8"))
                    meta.setdefault("title", titre)
                    body = texte.rstrip() + ("\n\n" + body.strip() if body.strip() else "") + "\n"
                    path = source
                out.append((page["key"], group, path, meta, body))
            for module in page["modules"].get(group, []):
                out += [(page["key"], group, p, m, b) for p, m, b in module_entries(module)]
    for _, _, path, meta, _ in out:
        if not meta.get("title"):
            raise BuildError(f"{path}: `title` manquant")
    return out


def relative(path):
    try:
        return depot_path(path)
    except ValueError:
        return str(path)


def load_sections(entries, renderer):
    sections = []
    for page, group, path, meta, body in entries:
        body_html, anchors = renderer.render(body, path, meta["id"])
        sections.append({
            "id": meta["id"],
            "page": page,
            "group": group,
            "subgroup": meta.get("subgroup"),
            "title": meta["title"],
            "nav": meta.get("nav"),
            "icon": None,
            "aka": None,
            "deprecie": False,
            "html": body_html,
            "anchors": anchors,
            "source": relative(path),
            "description": meta.get("description") or describe(body_html),
        })
    return sections


def load_lexique(renderer):
    path = CONTENT / "lexique.md"
    if not path.exists():
        return []
    terms = []
    parts = re.split(r"^## +(.+)$", path.read_text(encoding="utf-8"), flags=re.M)
    for term, body in zip(parts[1::2], parts[2::2]):
        term = term.strip()
        body_html, _ = renderer.render(body.strip(), path)
        target = re.search(r'href="#([\w-]+)"', body_html)
        terms.append({
            "t": term,
            "id": "lexterm-" + slugify(term),
            "html": body_html,
            "target": target.group(1) if target else None,
        })
    return sorted(terms, key=lambda e: slugify(e["t"]))


def check_ids_and_links(site, sections, lexique, renderer):
    known = {page["key"]: "page" for page in site["pages"]}
    for sec in sections:
        for anchor in [sec["id"], *sec["anchors"]]:
            if anchor in known:
                raise BuildError(f"{sec['source']}: id `{anchor}` déjà utilisé")
            known[anchor] = sec["source"]
    for entry in lexique:
        known[entry["id"]] = "lexique"
    broken = [f"{relative(src)}: lien vers #{target} introuvable"
              for src, target in renderer.links if target not in known]
    if broken:
        raise BuildError("\n".join(broken))


def git_dates(paths):
    """Date du dernier commit de chaque fichier (chemin dans le dépôt -> AAAA-MM-JJ), d'un seul git log."""
    try:
        out = subprocess.run(["git", "log", "--format=@%cs", "--name-only", "--", *paths],
                             cwd=DEPOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return {}
    dates, current = {}, None
    for line in out.splitlines():
        if line.startswith("@"):
            current = line[1:]
        elif line.strip():
            dates.setdefault(line.strip(), current)
    return dates


def describe(body_html):
    """Texte du premier paragraphe, sans balises, coupé à DESCRIPTION_MAX caractères."""
    m = re.search(r"<p>(.*?)</p>", body_html, re.S)
    if not m:
        return ""
    text = html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= DESCRIPTION_MAX:
        return text
    head = text[:DESCRIPTION_MAX]
    sentence = head.rfind(". ")
    if sentence >= DESCRIPTION_MAX // 2:
        return head[:sentence + 1]
    cut = head[:DESCRIPTION_MAX - 1].rsplit(" ", 1)[0].rstrip(" ,;:.(")
    return cut + "…"


def seo_head(title, description, url):
    title, description, url = (html.escape(v, quote=False).replace('"', "&quot;")
                               for v in (title, description, url))
    return (
        f"{GENERATED_MARK}\n"
        f"<title>{title}</title>\n"
        f'<meta name="description" content="{description}">\n'
        f'<link rel="canonical" href="{url}">\n'
        '<meta property="og:type" content="article">\n'
        '<meta property="og:site_name" content="tekio.org">\n'
        f'<meta property="og:title" content="{title}">\n'
        f'<meta property="og:description" content="{description}">\n'
        f'<meta property="og:url" content="{url}">\n'
        '<meta property="og:locale" content="fr_FR">\n'
        '<meta name="twitter:card" content="summary">'
    )


def write_pages(site, sections, lexique, dates):
    """Une page HTML par section et pour le lexique, puis sitemap.xml. Chaque page est le site
    complet (gabarit www/index.html) ouvert sur sa section, avec ses propres métadonnées et le
    contenu de la section en HTML statique, lisible sans JavaScript."""
    template = (WWW / "index.html").read_text(encoding="utf-8")
    if not SEO_BLOCK_RE.search(template) or '<main id="main-root"></main>' not in template:
        raise BuildError("www/index.html : bloc <!-- seo --> ou <main id=\"main-root\"> introuvable")
    for old in WWW.glob("*.html"):
        if old.name != "index.html" and GENERATED_MARK in old.read_text(encoding="utf-8"):
            old.unlink()

    today = datetime.date.today().isoformat()
    labels = {p["key"]: p["label"] for p in site["pages"]}
    pages = []
    for sec in sections:
        title = f"{sec['title']} | {SITE_NAME}"
        description = sec["description"] or f"{sec['title']} : {labels[sec['page']]}, dans {SITE_NAME}."
        body = (
            f'<section class="panel active"><div class="panel-header"><div class="panel-titles">'
            f'<h1>{html.escape(sec["title"])}</h1></div></div><div class="md">{sec["html"]}</div></section>'
        )
        pages.append((sec["id"], title, description, body, dates.get(sec["source"], today)))
    if lexique and "lexique" in labels:
        entries = "".join(
            f'<div class="lex-entry" id="{e["id"]}"><div class="lex-term">{html.escape(e["t"])}</div>'
            f'<div class="lex-def">{e["html"]}</div></div>' for e in lexique)
        body = f'<div class="page-main active"><div class="page-header"><h1>Lexique</h1></div>{entries}</div>'
        pages.append(("lexique", f"Lexique : termes de l'IA en entreprise | {SITE_NAME}",
                      f"Lexique des cas d'usage d'IA en entreprise : {len(lexique)} termes et sigles "
                      "(RAG, BM25, garde, LLM juge, MLflow...), chacun relié à la section qui le détaille.",
                      body, dates.get("site/content/lexique.md", today)))

    titles = [p[1] for p in pages]
    for page_id, title, description, body, _ in pages:
        if page_id in RESERVED_PAGES:
            raise BuildError(f"id `{page_id}` réservé : il donnerait la page www/{page_id}.html")
        if titles.count(title) > 1:
            raise BuildError(f"titre de page en double : {title}")
        out = SEO_BLOCK_RE.sub(lambda _: seo_head(title, description, f"{SITE_URL}{page_id}.html"), template)
        out = out.replace('<html lang="fr">', f'<html lang="fr" data-route="{page_id}">', 1)
        out = out.replace('<main id="main-root"></main>', f'<main id="main-root">{body}</main>', 1)
        (WWW / f"{page_id}.html").write_text(out, encoding="utf-8")

    urls = [(SITE_URL, max(dates.values(), default=today))]
    urls += [(f"{SITE_URL}{p[0]}.html", p[4]) for p in pages]
    (WWW / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{html.escape(u)}</loc><lastmod>{d}</lastmod></url>\n" for u, d in urls)
        + "</urlset>\n",
        encoding="utf-8",
    )
    return len(pages)


def copy_media(media):
    if MEDIA.exists():
        shutil.rmtree(MEDIA)
    for rel in sorted(media):
        dest = MEDIA / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(DEPOT / rel, dest)


def main():
    site = load_site()
    entries = content_entries(site)
    published = {relative(path): meta["id"] for _, _, path, meta, _ in entries}
    for _, _, path, meta, _ in entries:
        for suffixe, _, noms in PAGES_MODULE:
            if meta["id"].endswith(f"-{suffixe}") and path.parent.parent == MODULES:
                published.update({relative(path.parent / nom): meta["id"] for nom in noms})
    renderer = Renderer(published)
    sections = load_sections(entries, renderer)
    lexique = load_lexique(renderer)
    check_ids_and_links(site, sections, lexique, renderer)
    for sec in sections:
        del sec["anchors"]
    sources = sorted({sec["source"] for sec in sections} | {"site/content"})
    dates = git_dates(sources)
    page_count = write_pages(site, sections, lexique, dates)
    copy_media(renderer.media)
    for sec in sections:
        del sec["description"]
    updated = max(dates.values(), default=datetime.date.today().isoformat())
    data = {
        "title": site["title"],
        "updated": datetime.date.fromisoformat(updated).strftime("%d/%m/%Y"),
        "pages": site["pages"],
        "projets": site.get("projets", []),
        "sections": sections,
        "lexique": lexique,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        "// Généré par site/build/build.py depuis la documentation du dépôt : ne pas éditer à la main.\n"
        "const SITE = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8",
    )
    print(f"{OUTPUT.relative_to(DEPOT)} : {len(sections)} sections, {len(lexique)} termes, "
          f"{len(renderer.media)} images")
    print(f"site/www/*.html : {page_count} pages, site/www/sitemap.xml : {page_count + 1} URL")


if __name__ == "__main__":
    try:
        main()
    except BuildError as err:
        sys.exit(f"Erreur de build :\n{err}")
