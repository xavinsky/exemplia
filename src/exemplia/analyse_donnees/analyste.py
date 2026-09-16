"""Analyste de données : question en langage naturel → SQL validé → résultat → synthèse.

Le LLM ne calcule jamais : les chiffres viennent de la base, le LLM écrit la requête puis rédige la
synthèse du résultat affiché à côté, avec la requête, pour que l'utilisateur puisse vérifier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import mlflow
from mlflow.entities import SpanType
from pydantic import BaseModel, Field
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from exemplia.analyse_donnees.sql import TABLES_AUTORISEES, ErreurSQL, valider_sql
from exemplia.garde.chaine import MESSAGE_BLOCAGE_ENTREE, Garde
from exemplia.garde.prompts import CONSIGNE_CONTENU_NON_FIABLE, delimiter
from exemplia.socle import base_donnees as bd
from exemplia.socle import tracage
from exemplia.socle.llm import ClientLLM

DESCRIPTIONS = {
    "produits": "Catalogue. type : 'produit' ou 'abonnement'. prix en euros TTC.",
    "clients": "Clients. La colonne email n'est pas accessible.",
    "commandes": "Une ligne par commande. montant en euros TTC. date_livraison vide si non livrée.",
    "lignes_commande": "Produits de chaque commande avec quantité et prix unitaire.",
    "tickets": "Demandes au service client avec leur catégorie.",
}


def schema_documente() -> str:
    """Schéma lisible par le LLM, construit depuis les métadonnées SQLAlchemy."""
    blocs = []
    for table in bd.metadata.sorted_tables:
        if table.name not in TABLES_AUTORISEES:
            continue
        colonnes = []
        for c in table.columns:
            if c.name == "email":
                continue
            ligne = f"  - {c.name} ({c.type})"
            if c.foreign_keys:
                ligne += f" → {next(iter(c.foreign_keys)).target_fullname}"
            if c.comment:
                ligne += f" : {c.comment}"
            colonnes.append(ligne)
        blocs.append(f"{table.name} — {DESCRIPTIONS[table.name]}\n" + "\n".join(colonnes))
    return "\n\n".join(blocs)


class RequeteSQL(BaseModel):
    raisonnement: str = Field(description="Tables et jointures nécessaires, en une ou deux phrases")
    sql: str = Field(description="Une seule requête SELECT")


PROMPT_SQL = """Tu écris des requêtes SQL ({dialecte}) pour répondre aux questions sur les données
d'Entreprise Exemple. Une seule requête SELECT, uniquement sur les tables ci-dessous. Nomme les
colonnes calculées avec des alias explicites en français.

{schema}"""

PROMPT_SYNTHESE = f"""Tu rédiges en français une synthèse courte du résultat d'une requête, pour
répondre à la question posée. N'utilise que les chiffres présents dans le résultat : n'effectue
aucun calcul supplémentaire. Si le résultat ne permet pas de répondre, dis-le.

{CONSIGNE_CONTENU_NON_FIABLE}"""


@dataclass
class ResultatAnalyse:
    question: str
    sql: str = ""
    colonnes: list[str] = field(default_factory=list)
    lignes: list[list[Any]] = field(default_factory=list)
    synthese: str = ""
    erreurs: list[str] = field(default_factory=list)


class Analyste:
    def __init__(
        self,
        client_llm: ClientLLM,
        moteur_lecture: Engine,
        garde: Garde,
        dialecte: str = "postgres",
        tentatives: int = 2,
    ) -> None:
        self.llm = client_llm
        self.moteur = moteur_lecture
        self.garde = garde
        self.dialecte = dialecte
        self.tentatives = tentatives

    @mlflow.trace(name="analyse.repondre", span_type=SpanType.AGENT)
    def repondre(self, question: str) -> ResultatAnalyse:
        tracage.decrire_trace(tags={"exemple": "analyse_donnees"})
        resultat = ResultatAnalyse(question)
        entree = self.garde.verifier_entree(question)
        if entree.bloque:
            resultat.synthese = MESSAGE_BLOCAGE_ENTREE
            return resultat

        messages = [
            {
                "role": "system",
                "content": PROMPT_SQL.format(dialecte=self.dialecte, schema=schema_documente()),
            },
            {"role": "user", "content": entree.texte},
        ]
        for _ in range(self.tentatives):
            requete = self.llm.extraire(messages, RequeteSQL)
            try:
                resultat.sql = valider_sql(requete.sql, self.dialecte)
                resultat.colonnes, resultat.lignes = self._executer(resultat.sql)
                break
            except (ErreurSQL, SQLAlchemyError) as erreur:
                message = str(getattr(erreur, "orig", None) or erreur).splitlines()[0]
                resultat.erreurs.append(message)
                # Correction automatique : le LLM reçoit l'erreur et propose une nouvelle requête.
                messages += [
                    {"role": "assistant", "content": requete.model_dump_json()},
                    {"role": "user", "content": f"Cette requête a échoué : {message}. Corrige-la."},
                ]
        else:
            resultat.synthese = (
                "Je n'ai pas réussi à construire une requête valide pour cette question."
            )
            return resultat

        resultat.synthese = self._synthetiser(entree.texte, resultat)
        return resultat

    def _executer(self, sql: str) -> tuple[list[str], list[list[Any]]]:
        with mlflow.start_span(name="analyse.execution_sql", span_type=SpanType.TOOL) as span:
            span.set_inputs({"sql": sql})
            with self.moteur.connect() as cx:
                curseur = cx.execute(text(sql))
                colonnes = list(curseur.keys())
                lignes = [list(ligne) for ligne in curseur.fetchall()]
            span.set_outputs({"nb_lignes": len(lignes)})
        return colonnes, lignes

    def _synthetiser(self, question: str, resultat: ResultatAnalyse) -> str:
        tableau = (
            " | ".join(resultat.colonnes)
            + "\n"
            + "\n".join(" | ".join(str(v) for v in ligne) for ligne in resultat.lignes[:50])
        )
        if len(resultat.lignes) > 50:
            tableau += f"\n… {len(resultat.lignes) - 50} lignes supplémentaires non affichées"
        reponse = self.llm.discuter(
            [
                {"role": "system", "content": PROMPT_SYNTHESE},
                {
                    "role": "user",
                    "content": f"Question : {question}\n\n"
                    + delimiter("requete", resultat.sql)
                    + "\n\n"
                    + delimiter("resultat", tableau),
                },
            ]
        )
        return reponse.texte
