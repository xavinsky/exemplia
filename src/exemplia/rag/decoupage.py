"""Découpage des documents Markdown en passages.

On découpe d'abord par section (titres `##`), qui sont des unités de sens, puis par paragraphes
quand une section dépasse la taille cible. Chaque passage garde le titre du document et de la
section : ils sont ajoutés au texte indexé, car une section isolée (« Délai ») perd son sens.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from exemplia.socle.documents import Document


@dataclass(frozen=True)
class Passage:
    id: str
    document: str
    titre_document: str
    section: str
    acces: str
    texte: str

    @property
    def texte_indexe(self) -> str:
        return f"{self.titre_document} — {self.section}\n{self.texte}"


def _abrege(titre: str) -> str:
    """Titre de section réduit à un identifiant lisible (« 6. Abonnements » → « 6-abonnements »)."""
    sans_accent = unicodedata.normalize("NFKD", titre.lower())
    sans_accent = "".join(c for c in sans_accent if not unicodedata.combining(c))
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", sans_accent)).strip("-") or "section"


def decouper(document: Document, taille_max: int = 900, chevauchement: int = 1) -> list[Passage]:
    """Découpe un document en passages.

    L'identifiant d'un passage vient du nom du document et du titre de sa section, pas de son rang :
    ajouter ou retirer une section ne renomme pas les autres, ce qui permet à l'indexation de ne
    retraiter que ce qui a changé (`IndexHybride.synchroniser`).
    """
    passages: list[Passage] = []
    for section, corps in _sections(document.contenu):
        for i, morceau in enumerate(_morceaux(corps, taille_max, chevauchement)):
            passages.append(
                Passage(
                    id=f"{document.nom}#{_abrege(section)}#{i}",
                    document=document.nom,
                    titre_document=document.titre,
                    section=section if i == 0 else f"{section} (suite)",
                    acces=document.acces,
                    texte=morceau,
                )
            )
    return passages


def _sections(contenu: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    titre, lignes = "Introduction", []
    for ligne in contenu.splitlines():
        if m := re.match(r"^#{1,3}\s+(.*)", ligne):
            if "".join(lignes).strip():
                sections.append((titre, "\n".join(lignes).strip()))
            titre, lignes = m.group(1).strip(), []
        else:
            lignes.append(ligne)
    if "".join(lignes).strip():
        sections.append((titre, "\n".join(lignes).strip()))
    return sections


def _morceaux(corps: str, taille_max: int, chevauchement: int) -> list[str]:
    paragraphes = [p.strip() for p in re.split(r"\n\s*\n", corps) if p.strip()]
    morceaux: list[list[str]] = [[]]
    for paragraphe in paragraphes:
        courant = morceaux[-1]
        if courant and sum(len(p) for p in courant) + len(paragraphe) > taille_max:
            morceaux.append(courant[-chevauchement:] if chevauchement else [])
        morceaux[-1].append(paragraphe)
    return ["\n\n".join(m) for m in morceaux if m]
