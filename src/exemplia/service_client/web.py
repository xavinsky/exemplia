"""Interface du service client : conversation, confirmations d'actions, commandes du client.

L'authentification est simulée par le choix du client dans le menu latéral. Les sessions sont
stockées en base (`sessions.DepotSessions`).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import Engine, select

from exemplia.garde.chaine import garde_standard
from exemplia.service_client import outils
from exemplia.service_client.assistant import PERIMETRE, AssistantServiceClient, Session
from exemplia.service_client.sessions import DepotSessions, SessionInconnue
from exemplia.socle import base_donnees as bd
from exemplia.socle.llm import ClientLLM
from exemplia.socle.web import dep_client_llm, dep_moteur, gabarits, mesurer

routeur = APIRouter(prefix="/service-client")

# Demandes qui fonctionnent quel que soit le client connecté : l'assistant retrouve ses commandes.
MESSAGES_EXEMPLE = [
    "Où en est ma dernière commande ?",
    "Combien ai-je dépensé cette année ?",
    "Je voudrais annuler ma dernière commande.",
    "Quel est le délai pour retourner un article ?",
    "Je vais porter plainte si je ne suis pas remboursé.",
]


def dep_sessions(moteur: Annotated[Engine, Depends(dep_moteur)]) -> DepotSessions:
    return DepotSessions(moteur)


def _session(sessions: DepotSessions, session_id: str) -> Session:
    try:
        return sessions.charger(session_id)
    except SessionInconnue as erreur:
        raise HTTPException(404, "Session inconnue : rechargez la page.") from erreur


def construire_assistant(client_llm: ClientLLM, moteur: Engine) -> AssistantServiceClient:
    return AssistantServiceClient(client_llm, moteur, garde_standard(client_llm, PERIMETRE))


def dep_assistant(
    client_llm: Annotated[ClientLLM, Depends(dep_client_llm)],
    moteur: Annotated[Engine, Depends(dep_moteur)],
) -> AssistantServiceClient:
    return construire_assistant(client_llm, moteur)


def _contexte(request, moteur, session: Session, **autres):
    with moteur.connect() as cx:
        clients = cx.execute(select(bd.clients.c.id, bd.clients.c.nom)).all()
    return {
        "actif": "service_client",
        "clients": clients,
        "messages_exemple": MESSAGES_EXEMPLE,
        "session": session,
        "commandes": outils.rechercher_commandes(moteur, session.client_id),
        **autres,
    }


@routeur.get("")
def page(
    request: Request,
    moteur: Annotated[Engine, Depends(dep_moteur)],
    sessions: Annotated[DepotSessions, Depends(dep_sessions)],
    client: str = "C01",
):
    session = Session(client_id=client)
    sessions.enregistrer(session)
    return gabarits().TemplateResponse(
        request, "service_client/index.html", _contexte(request, moteur, session)
    )


@routeur.post("/message")
def message(
    request: Request,
    client_llm: Annotated[ClientLLM, Depends(dep_client_llm)],
    moteur: Annotated[Engine, Depends(dep_moteur)],
    sessions: Annotated[DepotSessions, Depends(dep_sessions)],
    session_id: Annotated[str, Form()],
    texte: Annotated[str, Form()],
):
    session = _session(sessions, session_id)
    # Le client compté est passé à l'assistant : les appels de la garde sont mesurés aussi.
    with mesurer(client_llm) as (client, mesure):
        evenements = construire_assistant(client, moteur).repondre(session, texte)
    sessions.enregistrer(session)
    return gabarits().TemplateResponse(
        request,
        "service_client/evenements.html",
        {"evenements": evenements, "session": session, "mesure": mesure},
    )


@routeur.post("/confirmer")
def confirmer(
    request: Request,
    assistant: Annotated[AssistantServiceClient, Depends(dep_assistant)],
    session_id: Annotated[str, Form()],
    action_id: Annotated[str, Form()],
    accepte: Annotated[bool, Form()],
    sessions: Annotated[DepotSessions, Depends(dep_sessions)],
):
    session = _session(sessions, session_id)
    evenements = assistant.confirmer(session, action_id, accepte)
    sessions.enregistrer(session)
    return gabarits().TemplateResponse(
        request,
        "service_client/evenements.html",
        {"evenements": evenements, "session": session},
    )
