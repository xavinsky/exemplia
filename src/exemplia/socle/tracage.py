"""Activation des traces MLflow pour tous les exemples.

Les appels au client OpenAI (donc Ollama et vLLM) et les graphes LangGraph sont tracés
automatiquement. Les étapes métier (recherche, outils, garde) le sont avec `@mlflow.trace`.
"""

import contextlib
import logging
import os

import mlflow

from exemplia.socle.config import parametres

journal = logging.getLogger(__name__)
_actif = False


def reponses_rapides() -> None:
    """Pour une application web : échouer vite si MLflow ne répond pas, plutôt que réessayer.

    Les scripts (expériences, évaluations) gardent les nouvelles tentatives par défaut de MLflow.
    """
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "3")


def decrire_trace(tags: dict | None = None, metadata: dict | None = None) -> None:
    """Décrit la trace en cours (tags, utilisateur, session).

    Sans trace active — traçage désactivé, tests, contrôle de la fonction de prédiction par
    `mlflow.genai.evaluate` — l'appel est sans effet, plutôt qu'un avertissement dans les journaux.
    """
    if mlflow.get_current_active_span() is None:
        return
    mlflow.update_current_trace(tags=tags or {}, metadata=metadata or {})


def activer(experience: str) -> bool:
    """Envoie les traces vers le serveur MLflow configuré, dans l'expérience donnée.

    Renvoie False sans lever d'erreur si le traçage est désactivé ou le serveur injoignable :
    une application ne doit pas tomber parce que son observabilité est indisponible.
    """
    global _actif
    p = parametres()
    if not p.tracage_actif:
        mlflow.tracing.disable()
        return False
    try:
        mlflow.set_tracking_uri(p.mlflow_tracking_uri)
        mlflow.set_experiment(experience)
    except Exception as erreur:  # noqa: BLE001 - toute erreur réseau ou serveur
        journal.warning("Traces MLflow désactivées (%s) : %s", p.mlflow_tracking_uri, erreur)
        mlflow.tracing.disable()
        return False
    if not _actif:
        mlflow.openai.autolog()
        # LangGraph absent ou version non prise en charge : les autres traces restent actives.
        with contextlib.suppress(Exception):
            mlflow.langchain.autolog()
        _actif = True
    return True
