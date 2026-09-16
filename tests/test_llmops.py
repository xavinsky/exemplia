from decimal import Decimal

import mlflow
import pytest

from exemplia.analyse_donnees.sql import valider_sql
from exemplia.conformite.analyse import lire_referentiel
from exemplia.garde.chaine import garde_standard
from exemplia.llmops import scorers as s
from exemplia.llmops.evaluer import EXEMPLES, _jeu_workflow, charger_jeu
from exemplia.socle.documents import charger_documents, document
from exemplia.workflow_agents.emails import EMAILS


def _appel(scorer_, **kwargs):
    return scorer_(**kwargs)


def test_jeux_bien_formes():
    for nom in ["service_client", "rag", "conformite", "analyse_donnees", "garde"]:
        jeu = charger_jeu(nom)
        assert jeu and all({"inputs", "expectations"} <= set(ligne) for ligne in jeu), nom
    assert set(EXEMPLES) == {
        "service_client",
        "rag",
        "conformite",
        "analyse_donnees",
        "garde",
        "workflow",
    }


def test_aucune_attente_nulle():
    """MLflow refuse une attente de valeur nulle : l'évaluation échouerait après les prédictions."""
    jeux = [charger_jeu(n) for n in ["service_client", "rag", "conformite", "garde"]]
    for ligne in [ligne for jeu in [*jeux, _jeu_workflow()] for ligne in jeu]:
        assert all(v is not None for v in ligne["expectations"].values()), ligne


def test_jeu_rag_coherent_avec_documents():
    documents = {d.nom: d.acces for d in charger_documents()}
    for ligne in charger_jeu("rag"):
        for nom in ligne["expectations"]["documents_attendus"]:
            assert nom in documents
            niveaux = ["public", "interne", "confidentiel"]
            assert niveaux.index(documents[nom]) <= niveaux.index(ligne["inputs"]["niveau_acces"])


def test_jeu_conformite_couvre_le_referentiel():
    codes = {r.code for r in lire_referentiel(document("referentiel-achats").contenu)}
    for ligne in charger_jeu("conformite"):
        assert set(ligne["expectations"]["verdicts"]) == codes


def test_sql_de_reference_valides():
    for ligne in charger_jeu("analyse_donnees"):
        valider_sql(ligne["expectations"]["sql_reference"])


def test_scorers_service_client():
    sorties = {"outils": ["detail_commande"], "action": None, "escalade": False}
    assert _appel(
        s.outils_attendus,
        outputs=sorties,
        expectations={"outils_attendus": ["detail_commande|rechercher_commandes"]},
    )
    assert not _appel(s.outils_attendus, outputs=sorties, expectations={"outils_attendus": []})
    assert _appel(s.outils_attendus, outputs=sorties, expectations={}) is None
    assert _appel(s.action_correcte, outputs=sorties, expectations={"action_attendue": "aucune"})


def test_scorers_rag():
    sorties = {
        "documents_retenus": ["faq", "politique-de-retour"],
        "niveaux_recuperes": ["public", "interne"],
        "sources": [],
    }
    assert (
        _appel(
            s.rappel_documents,
            outputs=sorties,
            expectations={"documents_attendus": ["politique-de-retour", "cgv"]},
        )
        == 0.5
    )
    assert not _appel(s.aucune_fuite_acces, inputs={"niveau_acces": "public"}, outputs=sorties)
    assert _appel(s.reponse_citee, outputs=sorties, expectations={"reponse_inconnue": True})


def test_normalisation_resultats_sql():
    assert s.normaliser_lignes([["retour", 60], ["compte", Decimal("60")]]) == s.normaliser_lignes(
        [[60.0, "compte"], [60, "Retour"]]
    )


def test_verdicts_corrects():
    sorties = {"verdicts": {"R1": "conforme", "R2": "absent"}}
    attendus = {"verdicts": {"R1": ["conforme"], "R2": ["non_conforme"]}}
    assert _appel(s.verdicts_corrects, outputs=sorties, expectations=attendus) == 0.5


def test_emails_attendus_complets():
    for e in EMAILS:
        assert {"demande", "action", "escalade"} <= set(e["attendu"])


def test_evaluation_mlflow_sans_modele(mlflow_isole):
    """La mécanique d'évaluation tourne de bout en bout avec la garde sans modèle."""
    mlflow.create_experiment("eval", artifact_location=(mlflow_isole / "a").as_uri())
    mlflow.set_experiment("eval")
    mlflow.tracing.enable()
    garde = garde_standard()

    def predire(texte: str) -> dict:
        return {"bloque": garde.verifier_entree(texte).bloque}

    jeu = [
        ligne
        for ligne in charger_jeu("garde")
        if ligne["expectations"].get("type") in (None, "injection")
    ]
    try:
        resultat = mlflow.genai.evaluate(data=jeu, predict_fn=predire, scorers=[s.blocage_correct])
    finally:
        mlflow.tracing.disable()
    assert resultat.metrics["blocage_correct/mean"] == pytest.approx(1.0)
