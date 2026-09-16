import itertools

import mlflow
import pytest

from exemplia.socle.llm import FauxClientLLM
from exemplia.tri_tickets import experiences
from exemplia.tri_tickets.modeles import Categorie, ClassifieurLLM, pipeline_tfidf


@pytest.fixture(scope="module")
def donnees():
    return experiences.jeu_de_donnees()


@pytest.fixture
def mlflow_local(mlflow_isole):
    mlflow.create_experiment("tri-tickets", artifact_location=(mlflow_isole / "artefacts").as_uri())
    mlflow.set_experiment("tri-tickets")


def test_jeu_stratifie_par_formulation(donnees):
    from exemplia.socle import entreprise

    assert 50 <= len(donnees.x_test) <= 70
    assert all(8 <= donnees.y_test.count(c) <= 16 for c in entreprise.CATEGORIES_TICKETS)
    modele_de = {t["texte"]: t["modele"] for t in entreprise.generer().tickets}
    formulations_train = {modele_de[x] for x in donnees.x_train}
    assert not formulations_train & {modele_de[x] for x in donnees.x_test}


def test_tfidf_generalise_partiellement(donnees):
    modele = pipeline_tfidf().fit(donnees.x_train, donnees.y_train)
    assert (modele.predict(donnees.x_test) == donnees.y_test).mean() > 0.6


def test_llm_prompt_delimite():
    client = FauxClientLLM([Categorie(categorie="retour")])
    classifieur = ClassifieurLLM("modele")
    classifieur.client = client
    assert classifieur.predict(None, ["Je veux renvoyer le Produit A"]) == ["retour"]
    assert "<ticket>" in client.appels[0]["messages"][0]["content"]


def test_cycle_mlops_complet(donnees, mlflow_local):
    reponses = itertools.cycle(["livraison", "retour", "facturation", "compte", "produit"])
    faux_llm = FauxClientLLM(
        [lambda m, o: Categorie(categorie=next(reponses))] * len(donnees.x_test)
    )

    tfidf = experiences.lancer_tfidf(donnees)
    llm = experiences.lancer_llm(donnees, client=faux_llm)
    assert tfidf.f1_macro > llm.f1_macro

    gagnant, version = experiences.promouvoir_champion([tfidf, llm])
    assert gagnant.approche == "tfidf"

    champion = mlflow.pyfunc.load_model(f"models:/{experiences.NOM_MODELE}@champion")
    prediction = champion.predict(["Mon colis n'est toujours pas arrivé"])
    assert list(prediction) == ["livraison"]

    run = mlflow.get_run(tfidf.run_id)
    assert "f1_macro" in run.data.metrics
    artefacts = {a.path for a in mlflow.MlflowClient().list_artifacts(tfidf.run_id)}
    assert {"matrice_confusion.png", "rapport_classification.json"} <= artefacts
