"""Explication « Comment ça marche ? » de chaque exemple, servie depuis son fichier Markdown.

Le texte et le diagramme vivent dans `<exemple>/comment-ca-marche.md` : ils se lisent dans le dépôt
comme dans l'interface, et se modifient sans toucher aux gabarits.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from markdown_it import MarkdownIt

PAQUET = Path(__file__).resolve().parents[1]
FICHIER = "comment-ca-marche.md"


@lru_cache
def _rendu() -> MarkdownIt:
    return MarkdownIt("commonmark").enable("table")


def chemin(exemple: str) -> Path:
    return PAQUET / exemple / FICHIER


@lru_cache
def markdown(exemple: str) -> str:
    """Contenu du fichier, ou chaîne vide pour une page qui n'en a pas (l'accueil)."""
    fichier = chemin(exemple)
    return fichier.read_text(encoding="utf-8") if fichier.is_file() else ""


@lru_cache
def html(exemple: str) -> str:
    """Explication convertie en HTML, titre de premier niveau retiré : il devient le libellé de la
    section repliable dans la page."""
    contenu = markdown(exemple)
    if not contenu:
        return ""
    corps = contenu.split("\n", 1)[1] if contenu.startswith("# ") else contenu
    return _rendu().render(corps)


def html_reponse(texte: str) -> str:
    """Réponse de modèle convertie en HTML : les modèles écrivent en Markdown (gras, listes) et
    l'affichage brut laisserait les astérisques visibles. Le HTML présent dans le texte est
    échappé, jamais interprété."""
    return _rendu().render(texte or "")


def exemples_expliques() -> list[str]:
    return sorted(d.name for d in PAQUET.iterdir() if (d / FICHIER).is_file())
