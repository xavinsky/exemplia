"""Lecture des documents Markdown de l'Entreprise Exemple (en-tête `titre` / `acces`)."""

from dataclasses import dataclass
from pathlib import Path

from exemplia.socle.config import parametres

NIVEAUX_ACCES = ["public", "interne", "confidentiel"]


@dataclass(frozen=True)
class Document:
    nom: str
    titre: str
    acces: str
    contenu: str


def _lire(chemin: Path) -> Document:
    brut = chemin.read_text(encoding="utf-8")
    entete: dict[str, str] = {}
    if brut.startswith("---\n"):
        bloc, _, brut = brut[4:].partition("\n---\n")
        for ligne in bloc.splitlines():
            cle, _, valeur = ligne.partition(":")
            entete[cle.strip()] = valeur.strip()
    acces = entete.get("acces", "confidentiel")
    if acces not in NIVEAUX_ACCES:
        raise ValueError(f"{chemin.name} : niveau d'accès inconnu « {acces} »")
    return Document(chemin.stem, entete.get("titre", chemin.stem), acces, brut.strip())


def charger_documents(dossier: Path | None = None) -> list[Document]:
    dossier = dossier or parametres().documents_dir
    return [_lire(c) for c in sorted(dossier.glob("*.md"))]


def document(nom: str, dossier: Path | None = None) -> Document:
    dossier = dossier or parametres().documents_dir
    return _lire(dossier / f"{nom}.md")


def accessible(document_acces: str, niveau_utilisateur: str) -> bool:
    return NIVEAUX_ACCES.index(document_acces) <= NIVEAUX_ACCES.index(niveau_utilisateur)
