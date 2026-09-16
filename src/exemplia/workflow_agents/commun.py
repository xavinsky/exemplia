"""État et nœuds partagés par le workflow déterministe et l'agent orchestrateur.

Les deux variantes traitent la même demande entrante (un email) et se terminent de la même façon :
validation humaine du brouillon, puis envoi, avec exécution éventuelle de l'action demandée.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, TypedDict

from langgraph.types import interrupt
from sqlalchemy import Engine, select

from exemplia.garde.controles import ControleInjection, Decision
from exemplia.service_client import outils
from exemplia.socle import base_donnees as bd

SEUIL_ESCALADE_EUROS = 300
MOTIF_RECOURS = "Menace de recours juridique."
# Écrit par le code quand l'email n'est pas traité automatiquement : aucun appel au LLM.
BROUILLON_ATTENTE = (
    "Bonjour,\n\nNous avons bien reçu votre message. Un conseiller l'examine et reviendra vers "
    "vous rapidement.\n\nCordialement,\nLe service client d'Entreprise Exemple"
)


class EtatDemande(TypedDict, total=False):
    expediteur: str
    objet: str
    corps: str
    client_id: str | None
    alertes: list[str]
    classification: dict[str, Any]
    extraction: dict[str, Any]
    faits: dict[str, Any]
    motifs_escalade: list[str]
    action_proposee: dict[str, str] | None
    brouillon: str
    decision: dict[str, Any]
    statut: str
    messages: list[dict[str, Any]]
    etapes: int


def email_en_texte(etat: EtatDemande) -> str:
    return f"De : {etat['expediteur']}\nObjet : {etat['objet']}\n\n{etat['corps']}"


def controler(moteur: Engine):
    """Identifie le client par son adresse et repère les tentatives d'injection dans l'email."""

    def noeud(etat: EtatDemande) -> EtatDemande:
        with moteur.connect() as cx:
            client_id = cx.scalar(
                select(bd.clients.c.id).where(
                    bd.clients.c.email == etat["expediteur"].strip().lower()
                )
            )
        alertes, motifs = [], []
        if client_id is None:
            motifs.append("Expéditeur inconnu : aucun client associé à cette adresse.")
        texte = f"{etat['objet']}\n{etat['corps']}"
        verdict = ControleInjection().verifier(texte, {})
        if verdict.decision == Decision.BLOQUER:
            alertes.append(f"Formulation d'injection détectée : « {verdict.details['motif']} ».")
            motifs.append("Email suspect (tentative d'injection).")
        if outils.motif_recours(texte):
            motifs.append(MOTIF_RECOURS)
        mise_a_jour: EtatDemande = {
            "client_id": client_id,
            "alertes": alertes,
            "motifs_escalade": motifs,
        }
        if not traitement_automatique(mise_a_jour):
            mise_a_jour["brouillon"] = BROUILLON_ATTENTE
        return mise_a_jour

    return noeud


def traitement_automatique(etat: EtatDemande) -> bool:
    """Un email d'expéditeur inconnu ou suspect va directement au conseiller, sans LLM."""
    return bool(etat.get("client_id")) and not etat.get("alertes")


def verifier_commande(
    moteur: Engine, client_id: str, commande_id: str | None, demande: str, aujourd_hui: date
) -> tuple[dict, list[str], dict | None]:
    """Faits vérifiés par le code sur la commande citée. Renvoie (faits, motifs d'escalade, action)."""
    if not commande_id:
        return {"commande": None}, [], None
    detail = outils.detail_commande(moteur, client_id, commande_id)
    if "erreur" in detail:
        return {"commande": None, "erreur": detail["erreur"]}, [], None
    faits: dict[str, Any] = {"commande": detail}
    motifs, action = [], None
    if demande == "annulation":
        eligibilite = outils.eligibilite_annulation(moteur, client_id, commande_id)
        faits["eligibilite"] = eligibilite.__dict__
        if eligibilite.possible:
            action = {"type": "annulation", "commande_id": detail["id"]}
    elif demande in ("retour", "reclamation"):
        eligibilite = outils.eligibilite_retour(moteur, client_id, commande_id, aujourd_hui)
        faits["eligibilite"] = eligibilite.__dict__
        if eligibilite.possible:
            action = {"type": "retour", "commande_id": detail["id"]}
        if float(detail["montant"]) > SEUIL_ESCALADE_EUROS:
            motifs.append(f"Remboursement potentiel supérieur à {SEUIL_ESCALADE_EUROS} €.")
    return faits, motifs, action


def validation_humaine(etat: EtatDemande) -> EtatDemande:
    """Pause du graphe : un conseiller relit, corrige ou rejette le brouillon."""
    decision = interrupt(
        {
            "brouillon": etat.get("brouillon", ""),
            "motifs_escalade": etat.get("motifs_escalade", []),
            "action_proposee": etat.get("action_proposee"),
        }
    )
    return {"decision": decision}


def envoyer(moteur: Engine, aujourd_hui: date):
    def noeud(etat: EtatDemande) -> EtatDemande:
        decision = etat["decision"]
        client_id = etat.get("client_id") or "inconnu"
        compte_rendu = []
        action = etat.get("action_proposee")
        if action and decision.get("executer_action") and etat.get("client_id"):
            try:
                if action["type"] == "annulation":
                    compte_rendu.append(
                        outils.executer_annulation(moteur, client_id, action["commande_id"])
                    )
                else:
                    compte_rendu.append(
                        outils.executer_retour(
                            moteur, client_id, action["commande_id"], etat["objet"], aujourd_hui
                        )
                    )
            except ValueError as erreur:
                compte_rendu.append(f"Action non effectuée : {erreur}")
        with moteur.begin() as cx:
            empreinte = hashlib.sha256(
                f"{etat['corps']}|{decision.get('texte', '')}".encode()
            ).hexdigest()
            outils.journaliser(
                cx,
                "conseiller",
                "reponse_email",
                client_id,
                f"email:{client_id}:{empreinte[:32]}",
                {"objet": etat["objet"], "reponse": decision.get("texte", "")},
            )
        return {"statut": "envoyee", "faits": {**etat.get("faits", {}), "execution": compte_rendu}}

    return noeud


def cloturer(etat: EtatDemande) -> EtatDemande:
    return {"statut": "rejetee"}


def apres_validation(etat: EtatDemande) -> str:
    return "envoyer" if etat["decision"].get("approuver") else "cloturer"


def json_lisible(donnees: Any) -> str:
    return json.dumps(donnees, ensure_ascii=False, indent=2, default=str)
