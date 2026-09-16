"""Workflow déterministe : les étapes sont fixées par le code, le LLM intervient à chaque étape.

    controler → classer → extraire → verifier → rediger → validation_humaine → envoyer | cloturer
         └── expéditeur inconnu ou email suspect ─────────────────┘

C'est l'architecture la plus courante en production : prévisible, testable étape par étape, coût
connu à l'avance (trois appels LLM par demande).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from exemplia.garde.prompts import CONSIGNE_CONTENU_NON_FIABLE, delimiter
from exemplia.socle.documents import document
from exemplia.socle.llm import ClientLLM
from exemplia.workflow_agents import commun
from exemplia.workflow_agents.commun import EtatDemande


class Classification(BaseModel):
    categorie: Literal["livraison", "retour", "facturation", "compte", "produit", "autre"]
    urgence: Literal["normale", "haute"]


class Extraction(BaseModel):
    commande_id: str | None = Field(description="Référence CMD-XXXX citée, sinon null")
    demande: Literal["annulation", "retour", "information", "reclamation", "autre"]
    resume: str = Field(description="La demande en une phrase")
    menace_juridique: bool = Field(
        description="Mention d'avocat, de plainte, d'association de consommateurs ou de tribunal"
    )


def _systeme(tache: str) -> dict:
    return {"role": "system", "content": f"{tache}\n\n{CONSIGNE_CONTENU_NON_FIABLE}"}


def construire_workflow(
    client_llm: ClientLLM, moteur: Engine, aujourd_hui: date | None = None, checkpointer=None
):
    aujourd_hui = aujourd_hui or date.today()
    politiques = "\n\n".join(
        delimiter("document", document(nom).contenu, nom=nom)
        for nom in (
            "politique-de-retour",
            "conditions-generales-de-vente",
            "guide-interne-service-client",
        )
    )

    def classer(etat: EtatDemande) -> EtatDemande:
        resultat = client_llm.extraire(
            [
                _systeme("Classe cet email de client par catégorie et urgence."),
                {"role": "user", "content": delimiter("email", commun.email_en_texte(etat))},
            ],
            Classification,
        )
        return {"classification": resultat.model_dump()}

    def extraire(etat: EtatDemande) -> EtatDemande:
        resultat = client_llm.extraire(
            [
                _systeme("Extrais les informations utiles au traitement de cet email."),
                {"role": "user", "content": delimiter("email", commun.email_en_texte(etat))},
            ],
            Extraction,
        )
        motifs = list(etat.get("motifs_escalade", []))
        if resultat.menace_juridique and commun.MOTIF_RECOURS not in motifs:
            motifs.append(commun.MOTIF_RECOURS)
        return {"extraction": resultat.model_dump(), "motifs_escalade": motifs}

    def verifier(etat: EtatDemande) -> EtatDemande:
        extraction = etat["extraction"]
        faits, motifs, action = commun.verifier_commande(
            moteur, etat["client_id"], extraction["commande_id"], extraction["demande"], aujourd_hui
        )
        return {
            "faits": faits,
            "motifs_escalade": etat.get("motifs_escalade", []) + motifs,
            "action_proposee": action,
        }

    def rediger(etat: EtatDemande) -> EtatDemande:
        reponse = client_llm.discuter(
            [
                _systeme(
                    "Tu rédiges le brouillon de réponse d'un conseiller du service client, en "
                    "français, courtois et précis. Le brouillon part par email : écris en texte "
                    "brut, sans Markdown ni astérisques de mise en forme. "
                    "Appuie-toi uniquement sur les faits vérifiés et "
                    "les politiques fournies. N'annonce aucune action comme effectuée, validée ou "
                    "engagée : une action éligible se formule au conditionnel ou comme une "
                    "proposition (« nous pouvons annuler votre commande »), le conseiller la "
                    "valide avant envoi. Si des motifs d'escalade existent, rédige une réponse "
                    "d'attente indiquant qu'un responsable reprend le dossier."
                ),
                {
                    "role": "user",
                    "content": "\n\n".join(
                        [
                            delimiter("email", commun.email_en_texte(etat)),
                            delimiter("faits_verifies", commun.json_lisible(etat.get("faits", {}))),
                            delimiter(
                                "motifs_escalade",
                                "\n".join(etat.get("motifs_escalade", [])) or "aucun",
                            ),
                            politiques,
                        ]
                    ),
                },
            ]
        )
        return {"brouillon": reponse.texte}

    def apres_controle(etat: EtatDemande) -> str:
        return "classer" if commun.traitement_automatique(etat) else "validation_humaine"

    graphe = StateGraph(EtatDemande)
    graphe.add_node("controler", commun.controler(moteur))
    graphe.add_node("classer", classer)
    graphe.add_node("extraire", extraire)
    graphe.add_node("verifier", verifier)
    graphe.add_node("rediger", rediger)
    graphe.add_node("validation_humaine", commun.validation_humaine)
    graphe.add_node("envoyer", commun.envoyer(moteur, aujourd_hui))
    graphe.add_node("cloturer", commun.cloturer)

    graphe.add_edge(START, "controler")
    graphe.add_conditional_edges("controler", apres_controle, ["classer", "validation_humaine"])
    graphe.add_edge("classer", "extraire")
    graphe.add_edge("extraire", "verifier")
    graphe.add_edge("verifier", "rediger")
    graphe.add_edge("rediger", "validation_humaine")
    graphe.add_conditional_edges(
        "validation_humaine", commun.apres_validation, ["envoyer", "cloturer"]
    )
    graphe.add_edge("envoyer", END)
    graphe.add_edge("cloturer", END)
    return graphe.compile(checkpointer=checkpointer or InMemorySaver())
