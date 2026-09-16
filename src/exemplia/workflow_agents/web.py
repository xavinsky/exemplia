"""Interface du workflow d'agents : traitement pas à pas, puis validation humaine."""

import uuid
from functools import lru_cache
from typing import Annotated

import mlflow
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from mlflow.entities import SpanType
from sqlalchemy import Engine
from sqlalchemy.engine import make_url

from exemplia.socle import tracage
from exemplia.socle.config import parametres
from exemplia.socle.llm import ClientLLM
from exemplia.socle.web import dep_client_llm, dep_moteur, gabarits, mesurer
from exemplia.workflow_agents.emails import EMAILS
from exemplia.workflow_agents.orchestrateur import construire_orchestrateur
from exemplia.workflow_agents.workflow import construire_workflow

routeur = APIRouter(prefix="/workflow")
CONSTRUCTEURS = {"workflow": construire_workflow, "orchestrateur": construire_orchestrateur}


@lru_cache
def dep_checkpointer():
    """État des traitements en pause : PostgreSQL, pour survivre au redémarrage de l'application
    et être partagé entre plusieurs processus. En mémoire si la base n'est pas PostgreSQL."""
    url = make_url(parametres().database_url)
    if not url.drivername.startswith("postgresql"):
        return InMemorySaver()
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(
        url.set(drivername="postgresql").render_as_string(hide_password=False),
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()
    return checkpointer


def _executer(graphe, entree, config, mode: str) -> list[tuple[str, dict]]:
    """Les nœuds sont tracés par l'autolog LangChain, sous ce span qui porte les tags de l'exemple.

    Le graphe compilé n'est pas une entrée du span : seule la demande traitée l'est, pour que les
    juges de surveillance aient un contenu lisible.
    """
    identifiant = config["configurable"]["thread_id"]
    with mlflow.start_span(name="workflow.executer", span_type=SpanType.CHAIN) as span:
        tracage.decrire_trace(
            tags={"exemple": "workflow_agents", "architecture": mode},
            metadata={"mlflow.trace.session": identifiant},
        )
        span.set_inputs({"demande": entree if isinstance(entree, dict) else str(entree)})
        etapes = []
        for mise_a_jour in graphe.stream(entree, config, stream_mode="updates"):
            for noeud, valeurs in mise_a_jour.items():
                if noeud != "__interrupt__":
                    etapes.append((noeud, valeurs or {}))
        etat = graphe.get_state(config).values
        span.set_outputs(
            {
                "brouillon": etat.get("brouillon", ""),
                "action_proposee": etat.get("action_proposee"),
                "motifs_escalade": etat.get("motifs_escalade", []),
                "etapes": [noeud for noeud, _ in etapes],
            }
        )
    return etapes


def _contexte(graphe, config, identifiant, mode, etapes):
    etat = graphe.get_state(config)
    return {
        "id": identifiant,
        "mode": mode,
        "etapes": etapes,
        "etat": etat.values,
        "en_attente": bool(etat.next),
    }


@routeur.get("")
def page(request: Request):
    return gabarits().TemplateResponse(
        request, "workflow_agents/index.html", {"actif": "workflow_agents", "emails": EMAILS}
    )


@routeur.post("/traiter")
def traiter(
    request: Request,
    client_llm: Annotated[ClientLLM, Depends(dep_client_llm)],
    moteur: Annotated[Engine, Depends(dep_moteur)],
    expediteur: Annotated[str, Form()],
    objet: Annotated[str, Form()],
    corps: Annotated[str, Form()],
    checkpointer: Annotated[object, Depends(dep_checkpointer)],
    mode: Annotated[str, Form()] = "workflow",
):
    mode = mode if mode in CONSTRUCTEURS else "workflow"
    # L'architecture fait partie de l'identifiant : le graphe se reconstruit à la validation.
    identifiant = f"{mode}-{uuid.uuid4().hex}"
    config = {"configurable": {"thread_id": identifiant}}
    with mesurer(client_llm) as (client, mesure):
        graphe = CONSTRUCTEURS[mode](client, moteur, checkpointer=checkpointer)
        etapes = _executer(
            graphe, {"expediteur": expediteur, "objet": objet, "corps": corps}, config, mode
        )
    return gabarits().TemplateResponse(
        request,
        "workflow_agents/traitement.html",
        _contexte(graphe, config, identifiant, mode, etapes) | {"mesure": mesure},
    )


@routeur.post("/valider")
def valider(
    request: Request,
    client_llm: Annotated[ClientLLM, Depends(dep_client_llm)],
    moteur: Annotated[Engine, Depends(dep_moteur)],
    checkpointer: Annotated[object, Depends(dep_checkpointer)],
    identifiant: Annotated[str, Form()],
    texte: Annotated[str, Form()] = "",
    approuver: Annotated[bool, Form()] = False,
    executer_action: Annotated[bool, Form()] = False,
):
    mode = identifiant.split("-", 1)[0]
    if mode not in CONSTRUCTEURS:
        raise HTTPException(404, "Traitement inconnu.")
    config = {"configurable": {"thread_id": identifiant}}
    decision = {"approuver": approuver, "texte": texte, "executer_action": executer_action}
    with mesurer(client_llm) as (client, mesure):
        graphe = CONSTRUCTEURS[mode](client, moteur, checkpointer=checkpointer)
        if not graphe.get_state(config).next:
            raise HTTPException(
                404, "Aucun traitement en attente de validation pour cet identifiant."
            )
        etapes = _executer(graphe, Command(resume=decision), config, mode)
    return gabarits().TemplateResponse(
        request,
        "workflow_agents/traitement.html",
        _contexte(graphe, config, identifiant, mode, etapes) | {"mesure": mesure},
    )
