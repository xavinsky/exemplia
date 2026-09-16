"""Interface de l'analyse de données."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import Engine

from exemplia.analyse_donnees.analyste import Analyste
from exemplia.analyse_donnees.sql import (
    COLONNES_INTERDITES,
    TABLES_AUTORISEES,
    dialecte_sqlglot,
)
from exemplia.garde.chaine import garde_standard
from exemplia.socle import base_donnees
from exemplia.socle import base_donnees as bd
from exemplia.socle.llm import ClientLLM
from exemplia.socle.web import dep_client_llm, gabarits, mesurer

routeur = APIRouter(prefix="/analyse")

QUESTIONS = [
    "Quel est le chiffre d'affaires par mois, hors commandes annulées ?",
    "Quels sont les 5 produits les plus vendus en quantité ?",
    "Combien de tickets par catégorie ?",
    "Quelle part des commandes livrées a été retournée ?",
    "Quels clients ont passé plus de 4 commandes ?",
]


def dep_moteur_lecture() -> Engine:
    return base_donnees.moteur_lecture()


def tables_interrogeables() -> list[tuple[str, str]]:
    """Ce que le SQL généré a le droit de lire, tel que la validation l'autorise."""
    return [
        (table.name, ", ".join(c.name for c in table.columns if c.name not in COLONNES_INTERDITES))
        for table in bd.metadata.sorted_tables
        if table.name in TABLES_AUTORISEES
    ]


@routeur.get("")
def page(request: Request):
    return gabarits().TemplateResponse(
        request,
        "analyse_donnees/index.html",
        {"actif": "analyse_donnees", "questions": QUESTIONS, "tables": tables_interrogeables()},
    )


@routeur.post("/question")
def question(
    request: Request,
    client_llm: Annotated[ClientLLM, Depends(dep_client_llm)],
    moteur: Annotated[Engine, Depends(dep_moteur_lecture)],
    question: Annotated[str, Form()],
):
    with mesurer(client_llm) as (client, mesure):
        garde = garde_standard(client, juge=False, masquer_donnees_personnelles=False)
        analyste = Analyste(client, moteur, garde, dialecte=dialecte_sqlglot(moteur.dialect.name))
        resultat = analyste.repondre(question)
    return gabarits().TemplateResponse(
        request, "analyse_donnees/resultat.html", {"r": resultat, "mesure": mesure}
    )
