"""Compare les approches de tri des tickets dans MLflow et promeut la meilleure en `champion`.

    uv run python -m exemplia.tri_tickets.experiences --approches tfidf embeddings llm

Chaque approche est un run de l'expérience `tri-tickets` avec les mêmes métriques, calculées sur le
même jeu de test, composé de formulations absentes de l'entraînement. Le modèle au meilleur F1 macro est enregistré dans le Model Registry
(`tri-tickets`) avec l'alias `champion`, que l'application charge.
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")

import mlflow  # noqa: E402
import mlflow.pyfunc  # noqa: E402
import mlflow.sklearn  # noqa: E402
from mlflow import MlflowClient  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    ConfusionMatrixDisplay,
    accuracy_score,
    classification_report,
    f1_score,
)
from sklearn.model_selection import StratifiedGroupKFold  # noqa: E402

from exemplia.socle import entreprise  # noqa: E402
from exemplia.socle.config import parametres  # noqa: E402
from exemplia.socle.llm import ClientLLM  # noqa: E402
from exemplia.tri_tickets.modeles import (  # noqa: E402
    CATEGORIES_TICKETS,
    NOM_PROMPT,
    PROMPT_ZERO_SHOT,
    ClassifieurEmbeddings,
    ClassifieurLLM,
    pipeline_tfidf,
)

EXPERIENCE = "tri-tickets"
NOM_MODELE = "tri-tickets"
ALIAS_CHAMPION = "champion"


@dataclass
class JeuDonnees:
    x_train: list[str]
    x_test: list[str]
    y_train: list[str]
    y_test: list[str]


@dataclass
class ResultatApproche:
    approche: str
    f1_macro: float
    exactitude: float
    latence_ms: float
    run_id: str
    model_uri: str


def jeu_de_donnees(graine: int = 42, nb_parts: int = 5) -> JeuDonnees:
    """Environ 20 % des tickets en test, stratifiés par catégorie.

    La séparation se fait par formulation d'origine : aucune tournure du test n'est vue à
    l'entraînement. Un découpage aléatoire mettrait des quasi-doublons des deux côtés et
    surestimerait les modèles qui mémorisent les mots (TF-IDF).
    """
    tickets = entreprise.generer().tickets
    x, y = [t["texte"] for t in tickets], [t["categorie"] for t in tickets]
    decoupage = StratifiedGroupKFold(n_splits=nb_parts, shuffle=True, random_state=graine)
    train, test = next(decoupage.split(x, y, groups=[t["modele"] for t in tickets]))
    return JeuDonnees(
        [x[i] for i in train], [x[i] for i in test], [y[i] for i in train], [y[i] for i in test]
    )


def _evaluer(nom: str, predire: Callable[[list[str]], list[str]], donnees: JeuDonnees) -> dict:
    debut = time.perf_counter()
    predictions = predire(donnees.x_test)
    latence_ms = (time.perf_counter() - debut) * 1000 / len(donnees.x_test)
    metriques = {
        "f1_macro": f1_score(donnees.y_test, predictions, average="macro"),
        "exactitude": accuracy_score(donnees.y_test, predictions),
        "latence_ms_par_ticket": latence_ms,
    }
    mlflow.log_metrics(metriques)
    mlflow.log_dict(
        classification_report(donnees.y_test, predictions, output_dict=True, zero_division=0),
        "rapport_classification.json",
    )
    affichage = ConfusionMatrixDisplay.from_predictions(
        donnees.y_test, predictions, labels=CATEGORIES_TICKETS, xticks_rotation=45
    )
    affichage.ax_.set_title(nom)
    mlflow.log_figure(affichage.figure_, "matrice_confusion.png")
    return metriques


def _resultat(approche, metriques, run, info) -> ResultatApproche:
    return ResultatApproche(
        approche,
        metriques["f1_macro"],
        metriques["exactitude"],
        metriques["latence_ms_par_ticket"],
        run.info.run_id,
        info.model_uri,
    )


def lancer_tfidf(donnees: JeuDonnees, c: float = 5.0) -> ResultatApproche:
    with mlflow.start_run(run_name="tfidf-regression") as run:
        mlflow.log_params({"approche": "tfidf", "C": c, "n_train": len(donnees.x_train)})
        modele = pipeline_tfidf(c).fit(donnees.x_train, donnees.y_train)
        metriques = _evaluer("TF-IDF + régression", lambda x: modele.predict(x).tolist(), donnees)
        info = mlflow.sklearn.log_model(modele, name="modele", input_example=[donnees.x_test[0]])
    return _resultat("tfidf", metriques, run, info)


def lancer_embeddings(
    donnees: JeuDonnees, client: ClientLLM | None = None, c: float = 5.0
) -> ResultatApproche:
    modele_embeddings = parametres().modele_embeddings
    with mlflow.start_run(run_name="embeddings-regression") as run:
        mlflow.log_params(
            {
                "approche": "embeddings",
                "modele_embeddings": modele_embeddings,
                "C": c,
                "n_train": len(donnees.x_train),
            }
        )
        classifieur = ClassifieurEmbeddings(modele_embeddings, c)
        classifieur.client = client
        classifieur.entrainer(donnees.x_train, donnees.y_train)
        metriques = _evaluer(
            "Embeddings + régression", lambda x: classifieur.predict(None, x), donnees
        )
        info = mlflow.pyfunc.log_model(name="modele", python_model=classifieur)
    return _resultat("embeddings", metriques, run, info)


def lancer_llm(donnees: JeuDonnees, client: ClientLLM | None = None) -> ResultatApproche:
    modele = parametres().modele_chat
    prompt = mlflow.genai.register_prompt(
        NOM_PROMPT, PROMPT_ZERO_SHOT, commit_message="Prompt de classification sans exemple"
    )
    with mlflow.start_run(run_name="llm-zero-shot") as run:
        mlflow.log_params({"approche": "llm", "modele": modele, "prompt": prompt.uri, "n_train": 0})
        classifieur = ClassifieurLLM(modele, prompt_uri=prompt.uri)
        classifieur.client = client
        metriques = _evaluer("LLM sans exemple", lambda x: classifieur.predict(None, x), donnees)
        info = mlflow.pyfunc.log_model(name="modele", python_model=classifieur)
    return _resultat("llm", metriques, run, info)


def resultats_experience() -> list[ResultatApproche]:
    """Tous les runs de l'expérience qui ont des métriques : la promotion les compare tous, y
    compris le fine-tuning, lancé à part."""
    client = MlflowClient()
    experience = client.get_experiment_by_name(EXPERIENCE)
    if experience is None:
        return []
    resultats = []
    for run in client.search_runs([experience.experiment_id]):
        if "f1_macro" not in run.data.metrics:
            continue
        resultats.append(
            ResultatApproche(
                run.data.params.get("approche", run.info.run_name),
                run.data.metrics["f1_macro"],
                run.data.metrics["exactitude"],
                run.data.metrics["latence_ms_par_ticket"],
                run.info.run_id,
                f"runs:/{run.info.run_id}/modele",
            )
        )
    return resultats


def promouvoir_champion(resultats: list[ResultatApproche]) -> tuple[ResultatApproche, str]:
    """Enregistre le meilleur modèle et lui donne l'alias `champion`.

    À F1 égal (à 1 point près), le plus rapide gagne : en production, un petit modèle aussi bon
    qu'un LLM coûte bien moins cher à servir.
    """
    meilleur_f1 = max(r.f1_macro for r in resultats)
    candidats = [r for r in resultats if r.f1_macro >= meilleur_f1 - 0.01]
    gagnant = min(candidats, key=lambda r: r.latence_ms)
    version = mlflow.register_model(gagnant.model_uri, NOM_MODELE)
    client = MlflowClient()
    client.set_registered_model_alias(NOM_MODELE, ALIAS_CHAMPION, version.version)
    client.set_model_version_tag(NOM_MODELE, version.version, "approche", gagnant.approche)
    return gagnant, version.version


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--approches",
        nargs="+",
        default=["tfidf", "embeddings", "llm"],
        choices=["tfidf", "embeddings", "llm"],
    )
    parser.add_argument("--sans-promotion", action="store_true")
    args = parser.parse_args()

    mlflow.set_tracking_uri(parametres().mlflow_tracking_uri)
    mlflow.set_experiment(EXPERIENCE)
    donnees = jeu_de_donnees()
    lanceurs = {"tfidf": lancer_tfidf, "embeddings": lancer_embeddings, "llm": lancer_llm}
    resultats = [lanceurs[a](donnees) for a in args.approches]
    for r in resultats:
        print(
            f"{r.approche:12} F1 macro {r.f1_macro:.3f}  exactitude {r.exactitude:.3f}  "
            f"{r.latence_ms:8.2f} ms/ticket"
        )
    if not args.sans_promotion:
        gagnant, version = promouvoir_champion(resultats)
        print(f"Champion : {gagnant.approche} (version {version} de {NOM_MODELE})")


if __name__ == "__main__":
    main()
