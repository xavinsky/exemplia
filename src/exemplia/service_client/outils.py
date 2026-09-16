"""Outils du service client : lecture des commandes et actions encadrées.

Le client connecté est toujours fourni par l'application, jamais par le LLM : un outil ne peut
donc renvoyer que les commandes de ce client. Les règles d'éligibilité sont vérifiées ici, dans le
code, et pas déléguées au modèle.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import Engine, and_, insert, select, update
from sqlalchemy.exc import IntegrityError

from exemplia.socle import base_donnees as bd
from exemplia.socle.llm import definition_outil

DELAI_RETOUR_JOURS = 30
Statut = Literal["en_preparation", "expediee", "livree", "annulee", "retournee"]


# --- Schémas des arguments, exposés au LLM ---------------------------------------------------


class RechercherCommandes(BaseModel):
    statut: Statut | None = Field(default=None, description="Filtrer sur un statut")


class CatalogueProduits(BaseModel):
    type: Literal["produit", "abonnement"] | None = Field(
        default=None, description="Filtrer sur les produits physiques ou les abonnements"
    )


class DetailCommande(BaseModel):
    commande_id: str = Field(description="Référence de commande, par exemple CMD-0012")


class ProposerAnnulation(BaseModel):
    commande_id: str = Field(description="Référence de la commande à annuler")


class ProposerRetour(BaseModel):
    commande_id: str = Field(description="Référence de la commande à retourner")
    # Facultatif : l'éligibilité se vérifie sans motif, le modèle n'a pas à le demander d'abord.
    motif: str = Field(default="", description="Motif du retour, si le client l'a donné")


class TransfererConseiller(BaseModel):
    motif: str = Field(description="Raison du transfert vers un conseiller humain")


OUTILS_LECTURE = {"rechercher_commandes", "detail_commande", "catalogue_produits"}
OUTILS_ECRITURE = {"proposer_annulation", "proposer_retour"}

DEFINITIONS_OUTILS = [
    definition_outil(
        "rechercher_commandes",
        "Historique complet des commandes du client connecté, de la plus récente à la plus "
        "ancienne, avec date, statut et montant. Sans filtre, toutes les commandes sont renvoyées, "
        "quelle que soit leur date.",
        RechercherCommandes,
    ),
    definition_outil(
        "detail_commande", "Détail d'une commande du client connecté.", DetailCommande
    ),
    definition_outil(
        "catalogue_produits",
        "Catalogue vendu par Entreprise Exemple : référence, libellé, type (produit ou abonnement) "
        "et prix unitaire de chaque article.",
        CatalogueProduits,
    ),
    definition_outil(
        "proposer_annulation",
        "Prépare l'annulation d'une commande. Le client devra confirmer : l'annulation n'est pas "
        "effectuée par cet outil.",
        ProposerAnnulation,
    ),
    definition_outil(
        "proposer_retour",
        "Prépare une demande de retour. Le client devra confirmer : la demande n'est pas "
        "effectuée par cet outil.",
        ProposerRetour,
    ),
    definition_outil(
        "transferer_conseiller",
        "Transfère la conversation à un conseiller humain.",
        TransfererConseiller,
    ),
]


# --- Lecture ---------------------------------------------------------------------------------


def _commande_du_client(moteur: Engine, client_id: str, commande_id: str) -> dict | None:
    with moteur.connect() as cx:
        ligne = (
            cx.execute(
                select(bd.commandes).where(
                    and_(
                        bd.commandes.c.id == commande_id.strip().upper(),
                        bd.commandes.c.client_id == client_id,
                    )
                )
            )
            .mappings()
            .first()
        )
    return dict(ligne) if ligne else None


def rechercher_commandes(moteur: Engine, client_id: str, statut: str | None = None) -> list[dict]:
    requete = select(
        bd.commandes.c.id,
        bd.commandes.c.date_commande,
        bd.commandes.c.statut,
        bd.commandes.c.montant,
    ).where(bd.commandes.c.client_id == client_id)
    if statut:
        requete = requete.where(bd.commandes.c.statut == statut)
    with moteur.connect() as cx:
        lignes = cx.execute(requete.order_by(bd.commandes.c.date_commande.desc())).mappings()
        return [_serialisable(dict(lg)) for lg in lignes]


def catalogue_produits(moteur: Engine, type_produit: str | None = None) -> list[dict]:
    """Catalogue complet : le même pour tous les clients, aucun filtre d'autorisation à appliquer."""
    requete = select(
        bd.produits.c.id, bd.produits.c.libelle, bd.produits.c.type, bd.produits.c.prix
    )
    if type_produit:
        requete = requete.where(bd.produits.c.type == type_produit)
    with moteur.connect() as cx:
        return [
            _serialisable(dict(lg))
            for lg in cx.execute(requete.order_by(bd.produits.c.id)).mappings()
        ]


def detail_commande(moteur: Engine, client_id: str, commande_id: str) -> dict:
    commande = _commande_du_client(moteur, client_id, commande_id)
    if commande is None:
        # Même réponse qu'une commande inexistante : on ne révèle pas les commandes des autres.
        return {"erreur": f"Commande {commande_id} introuvable pour ce client."}
    with moteur.connect() as cx:
        lignes = cx.execute(
            select(
                bd.produits.c.libelle,
                bd.produits.c.type,
                bd.lignes_commande.c.quantite,
                bd.lignes_commande.c.prix_unitaire,
            )
            .join(bd.produits, bd.produits.c.id == bd.lignes_commande.c.produit_id)
            .where(bd.lignes_commande.c.commande_id == commande["id"])
        ).mappings()
        commande["lignes"] = [_serialisable(dict(lg)) for lg in lignes]
    return _serialisable(commande)


# --- Éligibilité et exécution des actions ------------------------------------------------------


@dataclass
class Eligibilite:
    possible: bool
    raison: str
    recapitulatif: str = ""


def eligibilite_annulation(moteur: Engine, client_id: str, commande_id: str) -> Eligibilite:
    commande = _commande_du_client(moteur, client_id, commande_id)
    if commande is None:
        return Eligibilite(False, f"Commande {commande_id} introuvable pour ce client.")
    if commande["statut"] != "en_preparation":
        return Eligibilite(
            False,
            f"La commande {commande['id']} est au statut « {commande['statut']} » : seule une "
            "commande en préparation peut être annulée.",
        )
    return Eligibilite(
        True,
        "Commande en préparation.",
        f"Annuler la commande {commande['id']} du {commande['date_commande']:%d/%m/%Y} "
        f"({commande['montant']} €), remboursement intégral.",
    )


def eligibilite_retour(
    moteur: Engine, client_id: str, commande_id: str, aujourd_hui: date
) -> Eligibilite:
    commande = _commande_du_client(moteur, client_id, commande_id)
    if commande is None:
        return Eligibilite(False, f"Commande {commande_id} introuvable pour ce client.")
    if commande["statut"] != "livree" or commande["date_livraison"] is None:
        return Eligibilite(
            False,
            f"La commande {commande['id']} est au statut « {commande['statut']} » : seule une "
            "commande livrée peut être retournée.",
        )
    limite = commande["date_livraison"] + timedelta(days=DELAI_RETOUR_JOURS)
    if aujourd_hui > limite:
        return Eligibilite(
            False,
            f"Le délai de retour de {DELAI_RETOUR_JOURS} jours a expiré le {limite:%d/%m/%Y}.",
        )
    detail = detail_commande(moteur, client_id, commande["id"])
    physiques = [lg["libelle"] for lg in detail["lignes"] if lg["type"] == "produit"]
    if not physiques:
        return Eligibilite(False, "Les abonnements ne sont pas retournables : ils se résilient.")
    return Eligibilite(
        True,
        f"Livrée le {commande['date_livraison']:%d/%m/%Y}, retour possible jusqu'au "
        f"{limite:%d/%m/%Y}.",
        f"Demander le retour de la commande {commande['id']} ({', '.join(physiques)}). Une "
        "étiquette de retour prépayée sera envoyée par email.",
    )


def journaliser(cx, acteur: str, action: str, cible: str, cle: str, details: dict) -> bool:
    """Écrit dans le journal d'audit. Renvoie False si la clé d'idempotence existe déjà."""
    try:
        with cx.begin_nested():
            cx.execute(
                insert(bd.journal_actions).values(
                    horodatage=datetime.now(),
                    acteur=acteur,
                    action=action,
                    cible=cible,
                    cle_idempotence=cle,
                    details=json.dumps(details, default=str),
                )
            )
        return True
    except IntegrityError:
        return False


def executer_annulation(moteur: Engine, client_id: str, commande_id: str) -> str:
    eligibilite = eligibilite_annulation(moteur, client_id, commande_id)
    with moteur.begin() as cx:
        if not journaliser(
            cx,
            client_id,
            "annulation",
            commande_id,
            f"annulation:{commande_id}",
            {"canal": "assistant"},
        ):
            return f"L'annulation de la commande {commande_id} a déjà été enregistrée."
        if not eligibilite.possible:
            raise ValueError(eligibilite.raison)
        cx.execute(
            update(bd.commandes).where(bd.commandes.c.id == commande_id).values(statut="annulee")
        )
    return f"La commande {commande_id} est annulée. Le remboursement intégral est en cours."


def executer_retour(
    moteur: Engine, client_id: str, commande_id: str, motif: str, aujourd_hui: date
) -> str:
    eligibilite = eligibilite_retour(moteur, client_id, commande_id, aujourd_hui)
    with moteur.begin() as cx:
        if not journaliser(
            cx,
            client_id,
            "demande_retour",
            commande_id,
            f"retour:{commande_id}",
            {"motif": motif, "canal": "assistant"},
        ):
            return f"La demande de retour de la commande {commande_id} a déjà été enregistrée."
        if not eligibilite.possible:
            raise ValueError(eligibilite.raison)
    return (
        f"La demande de retour de la commande {commande_id} est enregistrée. L'étiquette "
        "prépayée arrive par email sous 24 heures."
    )


# Règle du guide interne : toute menace de recours part chez un conseiller. Vérifiée par le code
# avant le LLM, qui peut l'annoncer sans appeler l'outil de transfert.
MOTS_RECOURS = re.compile(
    r"\b(plainte|avocat|tribunal|justice|huissier|mise en demeure|litige|fraude|escroquerie|"
    r"associations? de consommateurs|ufc)\b"
)


def motif_recours(message: str) -> str | None:
    texte = unicodedata.normalize("NFKD", message.lower())
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    if trouve := MOTS_RECOURS.search(texte):
        return f"Menace de recours détectée : « {trouve.group(0)} »."
    return None


def transferer_conseiller(moteur: Engine, client_id: str, motif: str) -> str:
    with moteur.begin() as cx:
        journaliser(
            cx,
            client_id,
            "escalade",
            client_id,
            f"escalade:{client_id}:{datetime.now().isoformat()}",
            {"motif": motif},
        )
    return "Transfert enregistré : un conseiller reprend la conversation."


def _serialisable(d: dict) -> dict:
    return {
        k: (str(v) if not isinstance(v, (str, int, float, list, type(None))) else v)
        for k, v in d.items()
    }
