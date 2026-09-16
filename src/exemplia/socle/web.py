"""Briques web communes : gabarits Jinja partagés et catalogue des exemples."""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from sqlalchemy import Engine

from exemplia.socle import base_donnees, explications
from exemplia.socle.config import parametres
from exemplia.socle.llm import ClientJournal, ClientLLM, client_par_defaut

PAQUET = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Exemple:
    cle: str
    titre: str
    url: str
    resume: str
    technique: str


EXEMPLES = [
    Exemple(
        "service_client",
        "Service client",
        "/service-client",
        "Consulte les commandes et prépare des actions que le client confirme.",
        "Appel d'outils sur PostgreSQL, éligibilité en Python, garde et LLM juge.",
    ),
    Exemple(
        "rag",
        "RAG documentaire",
        "/rag",
        "Questions sur les documents internes, avec citations et droits d'accès.",
        "Qdrant dense + BM25, fusion RRF, reranker ONNX, filtre d'accès dans la requête.",
    ),
    Exemple(
        "conformite",
        "Conformité",
        "/conformite",
        "Vérification d'un contrat règle par règle contre un référentiel.",
        "Sortie structurée Pydantic par règle, citation vérifiée par le code.",
    ),
    Exemple(
        "analyse_donnees",
        "Analyse de données",
        "/analyse",
        "Questions en langage naturel traduites en SQL exécuté en lecture seule.",
        "Validation sqlglot (SELECT unique, tables autorisées), rôle lecteur.",
    ),
    Exemple(
        "tri_tickets",
        "Tri des tickets",
        "/tri-tickets",
        "Classification des tickets : ML classique contre LLM, cycle MLOps.",
        "scikit-learn, CamemBERT fine-tuné, LLM ; runs comparés, alias champion.",
    ),
    Exemple(
        "workflow_agents",
        "Workflow d'agents",
        "/workflow",
        "Traitement d'un email : workflow déterministe ou agent orchestrateur.",
        "Graphes LangGraph, pause avant envoi, checkpointer PostgreSQL.",
    ),
    Exemple(
        "garde",
        "Garde",
        "/garde",
        "Filtres d'entrée et de sortie, appliqués à tous les exemples.",
        "Règles, Presidio, Llama Guard 3, LLM juge ; verdicts tracés dans MLflow.",
    ),
]


def dep_moteur() -> Engine:
    """Dépendances FastAPI, remplaçables dans les tests (`app.dependency_overrides`)."""
    return base_donnees.moteur()


def dep_client_llm() -> ClientLLM:
    return client_par_defaut()


_liens_traces: dict[str, str] = {}


def lien_traces_mlflow(experience: str = "exemplia") -> str:
    """Onglet « Traces » de l'expérience dans MLflow, vide si le serveur est injoignable.

    L'identifiant d'expérience est demandé à MLflow une fois, puis gardé : une page ne doit pas
    échouer, ni ralentir, parce que l'observabilité est indisponible.
    """
    if experience not in _liens_traces:
        import mlflow

        p = parametres()
        try:
            mlflow.set_tracking_uri(p.mlflow_tracking_uri)
            trouvee = mlflow.get_experiment_by_name(experience)
        except Exception:  # noqa: BLE001 - serveur MLflow absent ou en erreur
            return ""
        if trouvee is None:
            return ""
        _liens_traces[experience] = (
            f"{p.mlflow_tracking_uri}/#/experiments/{trouvee.experiment_id}/traces"
        )
    return _liens_traces[experience]


@contextmanager
def mesurer(client_llm: ClientLLM) -> Iterator[tuple[ClientJournal, dict]]:
    """Compte les appels au modèle, mesure la durée et retient les échanges, pour les afficher.

    with mesurer(client_llm) as (client, mesure):
        reponse = composant(client).repondre(question)
    """
    compteur = ClientJournal(client_llm)
    mesure: dict[str, float | int] = {}
    debut = time.perf_counter()
    try:
        yield compteur, mesure
    finally:
        mesure.update(
            appels=compteur.appels,
            embeddings=compteur.appels_embeddings,
            duree_s=round(time.perf_counter() - debut, 1),
            echanges=compteur.echanges,
        )


@lru_cache
def gabarits() -> Jinja2Templates:
    """Gabarits du socle et de chaque exemple (`<module>/templates/<module>/*.html`)."""
    dossiers = [str(d) for d in sorted(PAQUET.glob("*/templates")) if d.is_dir()]
    moteur = Jinja2Templates(directory=dossiers)
    # Nommé `catalogue` et non `exemples` : une page qui passerait ses propres « exemples » au
    # gabarit masquerait la variable globale, et le menu de navigation disparaîtrait.
    moteur.env.globals["catalogue"] = EXEMPLES
    moteur.env.globals["explication_html"] = explications.html
    moteur.env.filters["markdown"] = lambda texte: Markup(explications.html_reponse(texte))
    moteur.env.globals["depot_url"] = parametres().depot_url
    moteur.env.globals["lien_traces_mlflow"] = lien_traces_mlflow
    return moteur
