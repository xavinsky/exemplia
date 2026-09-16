"""Interface du tri des tickets : prédiction par le modèle champion et comparaison des runs."""

import json
from functools import lru_cache
from typing import Annotated
from urllib.parse import urlencode

import mlflow
from fastapi import APIRouter, Depends, Form, Request
from mlflow import MlflowClient

from exemplia.socle.config import parametres
from exemplia.socle.llm import ClientLLM
from exemplia.socle.web import dep_client_llm, gabarits, mesurer
from exemplia.tri_tickets.experiences import ALIAS_CHAMPION, EXPERIENCE, NOM_MODELE
from exemplia.tri_tickets.modeles import NOM_PROMPT

routeur = APIRouter(prefix="/tri-tickets")

# Chaque essai est une ligne : un modèle, et le ticket. Les deux derniers tickets séparent les
# approches — le désaccord est vérifié sur les modèles entraînés — et l'essai qui doit se tromper
# est signalé par la couleur du bouton.
TICKETS_EXEMPLE = [
    {"texte": "Mon colis n'est toujours pas arrivé, pouvez-vous me dire où il en est ?"},
    {"texte": "Je souhaite renvoyer le produit, il ne me convient pas."},
    {"texte": "J'ai été débité deux fois pour la même commande."},
    {
        "texte": "Le colis est bien là, mais la notice annonce un autre modèle.",
        "essais": [
            {"libelle": "LLM", "approche": "llm"},
            {"libelle": "CamemBERT", "approche": "camembert", "erreur": True},
        ],
    },
    {
        "texte": "Ma commande est bien arrivée, mais je souhaite la renvoyer.",
        "essais": [
            {"libelle": "embeddings", "approche": "embeddings"},
            {"libelle": "TF-IDF", "approche": "tfidf", "erreur": True},
        ],
    },
]


def _brancher_client(modele, client) -> None:
    """Fait passer les appels du champion par le client journalisé, quand il en utilise un.

    Les approches servies (embeddings, LLM) appellent le serveur de modèles ; TF-IDF et CamemBERT
    calculent en local et n'ont pas de client : leur trace est alors vide, ce qui est l'information
    utile — cette prédiction n'a rien coûté.
    """
    interne = getattr(getattr(modele, "_model_impl", None), "python_model", None)
    if hasattr(interne, "client"):
        interne.client = client


@lru_cache
def _modele(reference: str):
    """Modèle chargé une fois par référence : alias `champion` ou identifiant de run."""
    if reference == ALIAS_CHAMPION:
        return mlflow.pyfunc.load_model(f"models:/{NOM_MODELE}@{ALIAS_CHAMPION}")
    return mlflow.pyfunc.load_model(f"runs:/{reference}/modele")


def _categorie(prediction) -> tuple[str, float | None]:
    """Chaque saveur MLflow a sa forme de sortie : liste, tableau NumPy, ou table avec un score."""
    if hasattr(prediction, "iloc"):  # transformers : une ligne par texte, label et score
        ligne = prediction.iloc[0]
        return str(ligne["label"]), float(ligne["score"])
    return str(list(prediction)[0]), None


def approches_comparees(client: MlflowClient, experience) -> list[dict]:
    """Le meilleur run de chaque approche, du meilleur F1 au moins bon.

    Les expériences sont rejouées plusieurs fois : sans ce regroupement, la comparaison afficherait
    deux lignes par approche.
    """
    meilleurs: dict[str, dict] = {}
    for run in client.search_runs([experience.experiment_id]):
        approche = run.data.params.get("approche")
        if approche is None or "f1_macro" not in run.data.metrics:
            continue
        candidat = {
            "approche": approche,
            "run_id": run.info.run_id,
            "f1_macro": run.data.metrics["f1_macro"],
            "exactitude": run.data.metrics["exactitude"],
            "latence": run.data.metrics["latence_ms_par_ticket"],
        }
        if approche not in meilleurs or candidat["f1_macro"] > meilleurs[approche]["f1_macro"]:
            meilleurs[approche] = candidat
    return sorted(meilleurs.values(), key=lambda a: a["f1_macro"], reverse=True)


def lien_comparaison(url_mlflow: str, experience_id: str, run_ids: list[str]) -> str:
    """Page de comparaison de MLflow, pré-remplie avec les runs affichés.

    L'identifiant de chaque run est tiré de MLflow à l'affichage de la page : rien à stocker, et le
    lien suit les expériences rejouées.
    """
    parametres_url = urlencode(
        {"runs": json.dumps(run_ids), "experiments": json.dumps([experience_id])}
    )
    return f"{url_mlflow}/#/compare-runs?{parametres_url}"


def lien_run(url_mlflow: str, experience_id: str, run_id: str) -> str:
    return f"{url_mlflow}/#/experiments/{experience_id}/runs/{run_id}"


def liens_mlflow(url: str, experience_id: str, run_ids: list[str]) -> list[tuple[str, str, str]]:
    """Ce que le projet utilise de MLflow, chacun à sa page : (libellé, url, ce qu'on y voit)."""
    return [
        (
            "Expérience tri-tickets",
            f"{url}/#/experiments/{experience_id}",
            "un run par approche, mêmes métriques, mêmes artefacts",
        ),
        (
            "Comparaison des runs",
            lien_comparaison(url, experience_id, run_ids),
            "coordonnées parallèles et nuages de points, métriques côte à côte",
        ),
        (
            f"Model Registry : {NOM_MODELE}",
            f"{url}/#/models/{NOM_MODELE}",
            f"les versions et l'alias {ALIAS_CHAMPION}, qui désigne le modèle servi",
        ),
        (
            f"Prompt Registry : {NOM_PROMPT}",
            f"{url}/#/prompts/{NOM_PROMPT}",
            "le prompt de classification, versionné et référencé par le modèle LLM",
        ),
    ]


def _etat_mlflow():
    url = parametres().mlflow_tracking_uri
    mlflow.set_tracking_uri(url)
    client = MlflowClient()
    experience = client.get_experiment_by_name(EXPERIENCE)
    approches = approches_comparees(client, experience) if experience else []
    for approche in approches:
        approche["lien"] = lien_run(url, experience.experiment_id, approche["run_id"])
    comparaison = (
        lien_comparaison(url, experience.experiment_id, [a["run_id"] for a in approches])
        if approches
        else ""
    )
    try:
        version = client.get_model_version_by_alias(NOM_MODELE, ALIAS_CHAMPION)
    except mlflow.exceptions.MlflowException:
        version = None
    liens = (
        liens_mlflow(url, experience.experiment_id, [a["run_id"] for a in approches])
        if approches
        else []
    )
    return approches, version, comparaison, liens


@routeur.get("")
def page(request: Request):
    contexte = {
        "actif": "tri_tickets",
        "mlflow_url": parametres().mlflow_tracking_uri,
        "tickets_exemple": TICKETS_EXEMPLE,
        "nom_modele": NOM_MODELE,
        "alias": ALIAS_CHAMPION,
    }
    try:
        approches, champion, comparaison, liens = _etat_mlflow()
        contexte |= {
            "approches": approches,
            "champion": champion,
            "comparaison": comparaison,
            "liens_mlflow": liens,
        }
    except Exception as erreur:  # noqa: BLE001 - serveur MLflow indisponible
        contexte["erreur"] = str(erreur).splitlines()[0]
    return gabarits().TemplateResponse(request, "tri_tickets/index.html", contexte)


@routeur.post("/predire")
def predire(
    request: Request,
    client_llm: Annotated[ClientLLM, Depends(dep_client_llm)],
    texte: Annotated[str, Form()],
    approche: Annotated[str, Form()] = ALIAS_CHAMPION,
):
    contexte: dict = {}
    try:
        approches, version, _, _ = _etat_mlflow()
        choisie = next((a for a in approches if a["run_id"] == approche), None)
        if approche == ALIAS_CHAMPION:
            if version is None:
                raise RuntimeError("Aucun modèle champion : lancez d'abord les expériences.")
            libelle = f"champion ({version.tags.get('approche', '?')})"
        elif choisie is None:
            raise RuntimeError("Approche inconnue : rechargez la page.")
        else:
            libelle = choisie["approche"]
        modele = _modele(approche)
        with mesurer(client_llm) as (client, mesure):
            _brancher_client(modele, client)
            categorie, score = _categorie(modele.predict([texte]))
        contexte = {
            "categorie": categorie,
            "score": score,
            "libelle": libelle,
            "mesure": mesure,
        }
    except Exception as erreur:  # noqa: BLE001
        contexte = {"erreur": str(erreur).splitlines()[0]}
    return gabarits().TemplateResponse(request, "tri_tickets/prediction.html", contexte)
