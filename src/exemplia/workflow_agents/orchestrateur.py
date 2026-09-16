"""Agent orchestrateur : un superviseur décide lui-même quels agents spécialisés consulter.

    controler → superviseur ⇄ agents (commandes, documentation, rédaction) → completer_brouillon
              → validation_humaine → …

Plus souple que le workflow (il s'adapte à des demandes imprévues, peut consulter deux fois le même
agent), mais moins prévisible : nombre d'appels variable, risque de boucle, d'où la limite
d'étapes. À réserver aux demandes dont on ne peut pas figer le déroulé.
"""

from __future__ import annotations

import json
from datetime import date

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from exemplia.garde.prompts import CONSIGNE_CONTENU_NON_FIABLE, delimiter
from exemplia.service_client import outils
from exemplia.socle.documents import document
from exemplia.socle.llm import AppelOutil, ClientLLM, definition_outil, message_outil
from exemplia.workflow_agents import commun
from exemplia.workflow_agents.commun import EtatDemande


class Question(BaseModel):
    question: str = Field(description="Question précise posée à l'agent")


class Consignes(BaseModel):
    consignes: str = Field(description="Points à couvrir dans la réponse au client")


class Escalade(BaseModel):
    motif: str


ACTIONS = ("annulation", "retour")


class Action(BaseModel):
    type: str = Field(description="annulation ou retour")
    commande_id: str


OUTILS_SUPERVISEUR = [
    definition_outil(
        "agent_commandes",
        "Agent qui consulte les commandes du client et vérifie l'éligibilité à une annulation ou "
        "un retour.",
        Question,
    ),
    definition_outil(
        "agent_documentation",
        "Agent qui répond à partir des politiques de l'entreprise (retours, CGV, guide interne).",
        Question,
    ),
    definition_outil(
        "agent_redaction", "Agent qui rédige le brouillon de réponse au client.", Consignes
    ),
    definition_outil(
        "proposer_action",
        "Propose au conseiller une action vérifiée éligible par l'agent commandes.",
        Action,
    ),
    definition_outil(
        "signaler_escalade", "Signale qu'un responsable doit reprendre le dossier.", Escalade
    ),
]

PROMPT_SUPERVISEUR = """Tu coordonnes le traitement d'un email reçu par le service client d'Entreprise
Exemple. Client identifié : {client_id}.

Consulte les agents utiles, dans l'ordre que tu juges pertinent :
- si le client demande une annulation ou un retour, fais vérifier l'éligibilité par agent_commandes,
  puis appelle proposer_action si l'action est possible ;
- signale une escalade en cas de menace juridique, de fraude ou de remboursement supérieur à
  {seuil} euros ;
- fais toujours rédiger le brouillon par agent_redaction, en dernier, avec des consignes précises.
Quand le brouillon est rédigé, termine par une phrase de synthèse sans appeler d'outil.

{consigne}"""


def construire_orchestrateur(
    client_llm: ClientLLM,
    moteur: Engine,
    aujourd_hui: date | None = None,
    max_etapes: int = 6,
    checkpointer=None,
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

    def agent_commandes(client_id: str, question: str) -> str:
        lecture = [
            d for d in outils.DEFINITIONS_OUTILS if d["function"]["name"] in outils.OUTILS_LECTURE
        ]
        outils_agent = lecture + [
            definition_outil(
                "verifier_eligibilite",
                "Vérifie si une commande peut être annulée ou retournée.",
                Action,
            )
        ]
        messages = [
            {
                "role": "system",
                "content": "Tu réponds aux questions sur les commandes du client à "
                f"l'aide des outils. Sois factuel et concis.\n\n{CONSIGNE_CONTENU_NON_FIABLE}",
            },
            {"role": "user", "content": question},
        ]
        for _ in range(3):
            reponse = client_llm.discuter(messages, outils=outils_agent)
            messages.append(reponse.message())
            if not reponse.appels_outils:
                return reponse.texte
            for appel in reponse.appels_outils:
                a = appel.arguments
                try:
                    if appel.nom == "rechercher_commandes":
                        resultat = outils.rechercher_commandes(moteur, client_id, a.get("statut"))
                    elif appel.nom == "detail_commande":
                        resultat = outils.detail_commande(moteur, client_id, a["commande_id"])
                    elif appel.nom == "verifier_eligibilite":
                        verif = (
                            outils.eligibilite_annulation(moteur, client_id, a["commande_id"])
                            if a.get("type") == "annulation"
                            else outils.eligibilite_retour(
                                moteur, client_id, a["commande_id"], aujourd_hui
                            )
                        )
                        resultat = verif.__dict__
                    else:
                        resultat = {"erreur": f"Outil inconnu : {appel.nom}"}
                except KeyError as erreur:
                    resultat = {"erreur": f"Argument manquant : {erreur}"}
                messages.append(
                    message_outil(appel, delimiter("resultat_outil", commun.json_lisible(resultat)))
                )
        return "L'agent commandes n'a pas pu conclure."

    def agent_documentation(question: str) -> str:
        return client_llm.discuter(
            [
                {
                    "role": "system",
                    "content": "Tu réponds uniquement à partir des documents fournis. "
                    f"Si la réponse n'y est pas, dis-le.\n\n{CONSIGNE_CONTENU_NON_FIABLE}\n\n{politiques}",
                },
                {"role": "user", "content": question},
            ]
        ).texte

    def agent_redaction(etat: EtatDemande, consignes: str, messages: list[dict]) -> str:
        # Les réponses des autres agents sont les seuls faits sur lesquels s'appuyer.
        faits = [m["content"] for m in messages if m.get("role") == "tool"]
        return client_llm.discuter(
            [
                {
                    "role": "system",
                    "content": "Tu rédiges le brouillon de réponse d'un conseiller, en "
                    "français, courtois et précis, uniquement à partir des faits recueillis. "
                    "Le brouillon part par email : écris en texte brut, sans Markdown ni "
                    "astérisques de mise en forme. "
                    "N'annonce aucune action comme effectuée : le conseiller valide avant envoi. "
                    "Si des motifs d'escalade existent, rédige une réponse d'attente indiquant "
                    "qu'un responsable reprend le dossier."
                    f"\n\n{CONSIGNE_CONTENU_NON_FIABLE}",
                },
                {
                    "role": "user",
                    "content": "\n\n".join(
                        [
                            delimiter("email", commun.email_en_texte(etat)),
                            delimiter("faits_recueillis", "\n\n".join(faits) or "aucun"),
                            delimiter(
                                "motifs_escalade",
                                "\n".join(etat.get("motifs_escalade", [])) or "aucun",
                            ),
                            delimiter("consignes", consignes),
                        ]
                    ),
                },
            ]
        ).texte

    def superviseur(etat: EtatDemande) -> EtatDemande:
        messages = etat.get("messages") or [
            {
                "role": "system",
                "content": PROMPT_SUPERVISEUR.format(
                    client_id=etat["client_id"],
                    seuil=commun.SEUIL_ESCALADE_EUROS,
                    consigne=CONSIGNE_CONTENU_NON_FIABLE,
                ),
            },
            {"role": "user", "content": delimiter("email", commun.email_en_texte(etat))},
        ]
        reponse = client_llm.discuter(messages, outils=OUTILS_SUPERVISEUR)
        return {"messages": [*messages, reponse.message()], "etapes": etat.get("etapes", 0) + 1}

    def agents(etat: EtatDemande) -> EtatDemande:
        messages = list(etat["messages"])
        dernier = messages[-1]
        mise_a_jour: EtatDemande = {}
        motifs = list(etat.get("motifs_escalade", []))
        for appel_brut in dernier.get("tool_calls", []):
            appel = AppelOutil(
                appel_brut["id"],
                appel_brut["function"]["name"],
                json.loads(appel_brut["function"]["arguments"]),
            )
            a = appel.arguments
            match appel.nom:
                case "agent_commandes":
                    resultat = agent_commandes(etat["client_id"], a.get("question", ""))
                case "agent_documentation":
                    resultat = agent_documentation(a.get("question", ""))
                case "agent_redaction":
                    resultat = agent_redaction(
                        {**etat, "motifs_escalade": motifs}, a.get("consignes", ""), messages
                    )
                    mise_a_jour["brouillon"] = resultat
                case "proposer_action" if a.get("type") not in ACTIONS:
                    resultat = {"possible": False, "raison": f"Action inconnue : {a.get('type')}."}
                case "proposer_action":
                    # Mêmes vérifications que le workflow (éligibilité, seuil d'escalade) : le
                    # superviseur ne peut pas forcer une action.
                    faits, nouveaux_motifs, action = commun.verifier_commande(
                        moteur, etat["client_id"], a.get("commande_id"), a["type"], aujourd_hui
                    )
                    if action:
                        mise_a_jour["action_proposee"] = action
                    motifs += [m for m in nouveaux_motifs if m not in motifs]
                    resultat = faits.get("eligibilite") or {
                        "possible": False,
                        "raison": faits.get("erreur", "Commande introuvable."),
                    }
                case "signaler_escalade":
                    motif = a.get("motif", "Escalade demandée par le superviseur.")
                    if motif not in motifs:
                        motifs.append(motif)
                    resultat = "Escalade enregistrée."
                case _:
                    resultat = f"Outil inconnu : {appel.nom}"
            texte = resultat if isinstance(resultat, str) else commun.json_lisible(resultat)
            messages.append(message_outil(appel, delimiter("resultat_outil", texte)))
        return {**mise_a_jour, "messages": messages, "motifs_escalade": motifs}

    def completer_brouillon(etat: EtatDemande) -> EtatDemande:
        """Garde-fou : le conseiller reçoit toujours un brouillon, même si le superviseur s'est
        arrêté sans consulter l'agent de rédaction."""
        if etat.get("brouillon"):
            return {}
        consignes = "Réponds à la demande du client à partir des faits recueillis."
        return {"brouillon": agent_redaction(etat, consignes, etat.get("messages", []))}

    def apres_controle(etat: EtatDemande) -> str:
        return "superviseur" if commun.traitement_automatique(etat) else "validation_humaine"

    def apres_superviseur(etat: EtatDemande) -> str:
        if etat["messages"][-1].get("tool_calls") and etat["etapes"] < max_etapes:
            return "agents"
        return "completer_brouillon"

    graphe = StateGraph(EtatDemande)
    graphe.add_node("controler", commun.controler(moteur))
    graphe.add_node("superviseur", superviseur)
    graphe.add_node("agents", agents)
    graphe.add_node("completer_brouillon", completer_brouillon)
    graphe.add_node("validation_humaine", commun.validation_humaine)
    graphe.add_node("envoyer", commun.envoyer(moteur, aujourd_hui))
    graphe.add_node("cloturer", commun.cloturer)

    graphe.add_edge(START, "controler")
    graphe.add_conditional_edges("controler", apres_controle, ["superviseur", "validation_humaine"])
    graphe.add_conditional_edges(
        "superviseur", apres_superviseur, ["agents", "completer_brouillon"]
    )
    graphe.add_edge("agents", "superviseur")
    graphe.add_edge("completer_brouillon", "validation_humaine")
    graphe.add_conditional_edges(
        "validation_humaine", commun.apres_validation, ["envoyer", "cloturer"]
    )
    graphe.add_edge("envoyer", END)
    graphe.add_edge("cloturer", END)
    return graphe.compile(checkpointer=checkpointer or InMemorySaver())
