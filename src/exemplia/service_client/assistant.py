"""Assistant du service client : boucle d'appel d'outils avec garde et confirmation des actions.

Déroulé d'un tour :
1. garde d'entrée sur le message du client ;
2. menace de recours repérée par le code : transfert immédiat à un conseiller, sans appel au LLM ;
3. boucle bornée : le LLM répond ou appelle des outils ;
   - outil de lecture : exécuté immédiatement ;
   - outil d'écriture : le code vérifie l'éligibilité et met l'action en attente de confirmation ;
   - transfert : la conversation est marquée pour un conseiller ;
4. garde de sortie sur la réponse finale, à laquelle sont fournis les documents, le fonctionnement
   de l'assistant et les résultats des outils du tour.

L'action n'est exécutée que par `confirmer`, appelé par l'interface quand le client clique sur
« Confirmer » : jamais sur la seule parole du LLM.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import mlflow
from mlflow.entities import SpanType
from sqlalchemy import Engine

from exemplia.garde.chaine import MESSAGE_BLOCAGE_ENTREE, MESSAGE_BLOCAGE_SORTIE, Garde
from exemplia.garde.prompts import CONSIGNE_CONTENU_NON_FIABLE, delimiter
from exemplia.service_client import outils
from exemplia.socle import tracage
from exemplia.socle.documents import document
from exemplia.socle.llm import AppelOutil, ClientLLM, message_outil

DOCUMENTS_CONNAISSANCES = ["conditions-generales-de-vente", "politique-de-retour", "faq"]
PERIMETRE = "service client d'Entreprise Exemple : commandes, livraisons, retours, factures, compte"
MESSAGE_TRANSFERT = "Conversation transférée à un conseiller."

# Donné au juge de sortie avec les documents : ce que l'assistant peut légitimement annoncer.
FONCTIONNEMENT = """Fonctionnement de l'assistant : il consulte les commandes du client connecté avec
des outils. Les annulations et retours qu'il prépare s'affichent avec un bouton « Confirmer » et ne
sont effectués qu'après ce clic du client. Il peut transférer la conversation à un conseiller."""

PROMPT_SYSTEME = """Tu es l'assistant du service client d'Entreprise Exemple. Nous sommes le {aujourd_hui}.

Règles :
- Réponds en français, avec courtoisie et concision.
- Tu as accès aux données ci-dessous par tes outils. Ne dis jamais à un client que tu n'y as pas
  accès et ne le renvoie pas vers son espace client pour une information que tes outils te donnent :
  - tout son historique de commandes, avec date, statut et montant (rechercher_commandes) ;
  - le détail d'une de ses commandes, avec les produits, quantités et prix (detail_commande) ;
  - le catalogue et les prix (catalogue_produits).
- Sers-toi de ces données pour répondre à la question posée, même si elle ne correspond à aucun
  outil : compte, compare, additionne, rapproche les résultats. Appelle plusieurs outils si besoin.
  N'invente jamais un statut, une date ou un montant qu'ils ne t'ont pas donné.
- Ne demande jamais au client une information que tu as déjà. Ses commandes sont listées plus bas :
  si une seule correspond à sa demande, pars de celle-là en la nommant (référence, date, montant,
  statut) pour qu'il puisse te corriger. Ne demande une précision que si plusieurs commandes
  peuvent correspondre, et cite alors celles qui sont en jeu.
- Quand les données ne permettent pas de répondre, dis-le en nommant, avec tes propres mots,
  l'information précise qui te manque, puis propose ce que tu peux réellement faire. Ne réponds
  jamais à côté et ne propose rien qui sorte des critères donnés par le client (budget, type de
  produit, délai).
- Pour annuler une commande ou demander un retour, appelle toujours proposer_annulation ou
  proposer_retour, sans demander de précision au préalable (le motif est facultatif). Appelle-les
  même si le statut que tu connais te laisse penser que l'action est impossible : c'est l'outil qui
  décide de l'éligibilité et qui donne la raison exacte d'un refus, jamais toi. Ces outils ne font que préparer l'action : le client la
  confirme avec le bouton « Confirmer » affiché sous ta réponse, dans cette conversation (ni email,
  ni espace client, ni notification). Ne dis jamais qu'une action est effectuée avant cette
  confirmation.
- Pour les questions générales, appuie-toi uniquement sur les documents ci-dessous.
- Tu ne peux accorder ni geste commercial ni remboursement hors procédure.
- Une question sans rapport avec le service client d'Entreprise Exemple ({perimetre}) : décline
  poliment, sans y répondre.
- Utilise transferer_conseiller si le client le demande, ou s'il évoque une plainte, un avocat, une
  association de consommateurs, un tribunal, un litige ou une fraude.

{consigne}

{documents}

Commandes du client connecté, les plus récentes d'abord. Tu les as déjà : ne lui demande jamais sa
référence de commande, cite celle qui correspond à sa demande.
{commandes}"""


@dataclass
class ActionEnAttente:
    id: str
    type: str  # "annulation" ou "retour"
    commande_id: str
    recapitulatif: str
    motif: str = ""


def fenetre_conversation(historique: list[dict[str, Any]], tours: int) -> list[dict[str, Any]]:
    """Les `tours` derniers échanges, en commençant toujours par un message du client.

    Couper ailleurs laisserait un résultat d'outil orphelin, que l'API refuse.
    """
    debuts = [i for i, message in enumerate(historique) if message.get("role") == "user"]
    return historique if len(debuts) <= tours else historique[debuts[-tours] :]


@dataclass
class Evenement:
    """Élément affiché dans l'interface : message, appel d'outil, verdict de garde..."""

    type: str  # utilisateur, assistant, outil, garde, systeme
    texte: str
    details: dict[str, Any] = field(default_factory=dict)


# Le juge de sortie reçoit les résultats d'outils de toute la conversation, pas seulement du tour
# en cours : le client peut se référer à une commande consultée trois messages plus tôt. Les plus
# anciens sont oubliés pour que le prompt du juge reste borné.
MEMOIRE_RESULTATS_OUTILS = 12

# Tours de conversation envoyés au modèle. Le serveur de modèles tronque sans prévenir au-delà de
# sa fenêtre de contexte : au bout de quelques échanges, il ne reste plus la place d'écrire la
# réponse, qui s'arrête au milieu d'une phrase.
FENETRE_TOURS = 5

# Commandes du client placées dans le prompt système ; au-delà, l'outil prend le relais.
COMMANDES_EN_CONTEXTE = 10


@dataclass
class Session:
    client_id: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    historique: list[dict[str, Any]] = field(default_factory=list)
    resultats_outils: list[str] = field(default_factory=list)
    action_en_attente: ActionEnAttente | None = None
    escalade: bool = False


class AssistantServiceClient:
    def __init__(
        self,
        client_llm: ClientLLM,
        moteur: Engine,
        garde: Garde,
        aujourd_hui: date | None = None,
        max_tours: int = 5,
        fenetre_tours: int = FENETRE_TOURS,
    ) -> None:
        self.llm = client_llm
        self.moteur = moteur
        self.garde = garde
        self.aujourd_hui = aujourd_hui or date.today()
        self.max_tours = max_tours
        self.fenetre_tours = fenetre_tours
        self._sources = [document(nom).contenu for nom in DOCUMENTS_CONNAISSANCES]
        documents = "\n\n".join(
            delimiter("document", contenu, nom=nom)
            for nom, contenu in zip(DOCUMENTS_CONNAISSANCES, self._sources, strict=True)
        )
        self._gabarit_prompt = PROMPT_SYSTEME.format(
            aujourd_hui=f"{self.aujourd_hui:%d/%m/%Y}",
            perimetre=PERIMETRE,
            consigne=CONSIGNE_CONTENU_NON_FIABLE,
            documents=documents,
            commandes="{commandes}",
        )
        # Le contrôle de fuite ne porte que sur les consignes : citer les documents publics ou
        # rappeler le périmètre de l'assistant est le comportement attendu.
        self._consignes = PROMPT_SYSTEME.format(
            aujourd_hui="",
            perimetre="",
            consigne=CONSIGNE_CONTENU_NON_FIABLE,
            documents="",
            commandes="",
        )

    def commandes_en_contexte(self, session: Session) -> str:
        """Les commandes du client, telles qu'elles sont données au modèle.

        Elles sont dans le prompt plutôt qu'attendues d'un appel d'outil : sans elles sous les yeux,
        le modèle réclame au client une référence qu'il a déjà, même quand le client n'a qu'une
        seule commande.
        """
        commandes = outils.rechercher_commandes(self.moteur, session.client_id)
        lignes = [
            f"- {c['id']} du {c['date_commande']} : {c['statut']}, {c['montant']} €"
            for c in commandes[:COMMANDES_EN_CONTEXTE]
        ]
        if len(commandes) > COMMANDES_EN_CONTEXTE:
            lignes.append(
                f"- … {len(commandes) - COMMANDES_EN_CONTEXTE} commandes plus anciennes, "
                "à récupérer avec rechercher_commandes"
            )
        return "\n".join(lignes) or "- aucune commande"

    def prompt_systeme(self, session: Session) -> str:
        """Consignes, documents et commandes du client connecté."""
        return self._gabarit_prompt.replace("{commandes}", self.commandes_en_contexte(session))

    @mlflow.trace(name="service_client.repondre", span_type=SpanType.AGENT)
    def repondre(self, session: Session, message: str) -> list[Evenement]:
        tracage.decrire_trace(
            tags={"exemple": "service_client"},
            metadata={"mlflow.trace.user": session.client_id, "mlflow.trace.session": session.id},
        )
        evenements = [Evenement("utilisateur", message)]

        entree = self.garde.verifier_entree(message)
        if entree.bloque:
            evenements.append(Evenement("garde", entree.raison))
            evenements.append(Evenement("assistant", MESSAGE_BLOCAGE_ENTREE))
            return evenements
        if entree.texte != message:
            evenements.append(Evenement("garde", "Données personnelles masquées avant envoi."))
        session.historique.append({"role": "user", "content": entree.texte})
        session.action_en_attente = None

        if motif := outils.motif_recours(entree.texte):
            return evenements + self._transferer(session, motif)

        for _ in range(self.max_tours):
            reponse = self.llm.discuter(
                [
                    {"role": "system", "content": self.prompt_systeme(session)},
                    *fenetre_conversation(session.historique, self.fenetre_tours),
                ],
                outils=outils.DEFINITIONS_OUTILS,
            )
            session.historique.append(reponse.message())
            if not reponse.appels_outils:
                return evenements + self._finaliser(session, entree.texte, reponse.texte)
            for appel in reponse.appels_outils:
                resultat = self._executer_outil(session, appel)
                evenements.append(
                    Evenement(
                        "outil", appel.nom, {"arguments": appel.arguments, "resultat": resultat}
                    )
                )
                session.resultats_outils = [
                    *session.resultats_outils[-(MEMOIRE_RESULTATS_OUTILS - 1) :],
                    f"Résultat de l'outil {appel.nom} : {_texte(resultat)}",
                ]
                session.historique.append(
                    message_outil(appel, delimiter("resultat_outil", _texte(resultat)))
                )

        session.escalade = True
        texte = "Je n'arrive pas à traiter votre demande. Je vous transfère à un conseiller."
        session.historique.append({"role": "assistant", "content": texte})
        return evenements + [Evenement("assistant", texte), Evenement("systeme", MESSAGE_TRANSFERT)]

    def _finaliser(self, session: Session, question: str, texte: str) -> list[Evenement]:
        # Le juge vérifie la réponse contre tout ce que le modèle a reçu : documents, fonctionnement
        # de l'assistant et résultats des outils de la conversation (statuts, dates, éligibilité).
        sortie = self.garde.verifier_sortie(
            texte,
            {
                "question": question,
                # Le juge reçoit exactement ce que le modèle avait : documents, fonctionnement,
                # commandes du client et résultats d'outils. Sans les commandes, il prend pour une
                # invention une réponse fondée sur le contexte.
                "sources": [
                    *self._sources,
                    FONCTIONNEMENT,
                    f"Commandes du client {session.client_id} :\n"
                    + self.commandes_en_contexte(session),
                    *session.resultats_outils,
                ],
                "prompt_systeme": self._consignes,
            },
        )
        if not sortie.bloque:
            return [Evenement("assistant", texte)]
        session.escalade = True
        session.historique[-1] = {"role": "assistant", "content": MESSAGE_BLOCAGE_SORTIE}
        return [
            Evenement("garde", sortie.raison),
            Evenement("assistant", MESSAGE_BLOCAGE_SORTIE),
            Evenement("systeme", MESSAGE_TRANSFERT),
        ]

    def _transferer(self, session: Session, motif: str) -> list[Evenement]:
        session.escalade = True
        resultat = outils.transferer_conseiller(self.moteur, session.client_id, motif)
        texte = (
            "Je transmets votre demande à un conseiller, qui reprend le dossier et reviendra vers "
            "vous rapidement."
        )
        session.historique.append({"role": "assistant", "content": texte})
        return [
            Evenement(
                "outil",
                "transferer_conseiller",
                {"arguments": {"motif": motif}, "resultat": resultat, "automatique": True},
            ),
            Evenement("assistant", texte),
            Evenement("systeme", MESSAGE_TRANSFERT),
        ]

    def _executer_outil(self, session: Session, appel: AppelOutil) -> Any:
        with mlflow.start_span(name=appel.nom, span_type=SpanType.TOOL) as span:
            span.set_inputs(appel.arguments)
            try:
                resultat = self._dispatcher(session, appel)
            except (ValueError, TypeError) as erreur:
                resultat = {"erreur": f"Arguments invalides : {erreur}"}
            span.set_outputs({"resultat": resultat})
        return resultat

    def _dispatcher(self, session: Session, appel: AppelOutil) -> Any:
        a, m, c = appel.arguments, self.moteur, session.client_id
        match appel.nom:
            case "rechercher_commandes":
                return outils.rechercher_commandes(m, c, outils.RechercherCommandes(**a).statut)
            case "detail_commande":
                return outils.detail_commande(m, c, outils.DetailCommande(**a).commande_id)
            case "catalogue_produits":
                return outils.catalogue_produits(m, outils.CatalogueProduits(**a).type)
            case "proposer_annulation":
                args = outils.ProposerAnnulation(**a)
                eligibilite = outils.eligibilite_annulation(m, c, args.commande_id)
                return self._mettre_en_attente(session, "annulation", args.commande_id, eligibilite)
            case "proposer_retour":
                args = outils.ProposerRetour(**a)
                eligibilite = outils.eligibilite_retour(m, c, args.commande_id, self.aujourd_hui)
                return self._mettre_en_attente(
                    session, "retour", args.commande_id, eligibilite, args.motif
                )
            case "transferer_conseiller":
                session.escalade = True
                return outils.transferer_conseiller(m, c, outils.TransfererConseiller(**a).motif)
            case _:
                return {"erreur": f"Outil inconnu : {appel.nom}"}

    def _mettre_en_attente(self, session, type_action, commande_id, eligibilite, motif=""):
        if not eligibilite.possible:
            return {"possible": False, "raison": eligibilite.raison}
        session.action_en_attente = ActionEnAttente(
            id=uuid.uuid4().hex,
            type=type_action,
            commande_id=commande_id.strip().upper(),
            recapitulatif=eligibilite.recapitulatif,
            motif=motif,
        )
        return {
            "possible": True,
            "statut": "en_attente_confirmation_du_client",
            "recapitulatif": eligibilite.recapitulatif,
            "confirmation": "Le client confirme avec le bouton « Confirmer » affiché sous ta "
            "réponse. Pas d'email ni d'espace client pour cette étape.",
        }

    @mlflow.trace(name="service_client.confirmer", span_type=SpanType.TOOL)
    def confirmer(self, session: Session, action_id: str, accepte: bool) -> list[Evenement]:
        action = session.action_en_attente
        if action is None or action.id != action_id:
            return [Evenement("systeme", "Aucune action en attente correspondante.")]
        session.action_en_attente = None
        if not accepte:
            texte = "D'accord, je n'effectue pas cette action."
        else:
            try:
                if action.type == "annulation":
                    texte = outils.executer_annulation(
                        self.moteur, session.client_id, action.commande_id
                    )
                else:
                    texte = outils.executer_retour(
                        self.moteur,
                        session.client_id,
                        action.commande_id,
                        action.motif,
                        self.aujourd_hui,
                    )
            except ValueError as erreur:
                texte = f"L'action n'a pas pu être effectuée : {erreur}"
        # Le résultat réel est ajouté à l'historique pour que le LLM en tienne compte ensuite.
        session.historique.append({"role": "assistant", "content": texte})
        return [Evenement("assistant", texte)]


def _texte(resultat: Any) -> str:
    return (
        resultat
        if isinstance(resultat, str)
        else json.dumps(resultat, ensure_ascii=False, default=str)
    )
