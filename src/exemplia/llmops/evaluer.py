"""Évaluation des exemples sur leurs jeux de test, résultats et traces dans MLflow.

    uv run python -m exemplia.llmops.evaluer rag
    uv run python -m exemplia.llmops.evaluer service_client conformite analyse_donnees garde workflow

Nécessite les services (PostgreSQL chargé, Qdrant indexé, MLflow) et les modèles. Chaque exemple
crée un run dans l'expérience `evaluation-<exemple>` : on compare les runs après chaque changement
de prompt, de modèle ou de paramètre.

Les jeux du service client et du workflow supposent les données dans leur état initial : ils citent
des commandes dont le statut détermine le résultat attendu. Après une démonstration qui a annulé ou
retourné une commande, relancer avec `--recharger`.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable
from pathlib import Path

import mlflow
import pandas as pd
from sqlalchemy import text

from exemplia.llmops import scorers as s
from exemplia.socle.config import RACINE, parametres

DOSSIER_JEUX = RACINE / "evaluation"


def charger_jeu(nom: str, dossier: Path = DOSSIER_JEUX) -> list[dict]:
    with (dossier / f"{nom}.jsonl").open(encoding="utf-8") as fichier:
        return [json.loads(ligne) for ligne in fichier if ligne.strip()]


def evaluer_service_client():
    from exemplia.garde.chaine import garde_standard
    from exemplia.service_client.assistant import PERIMETRE, AssistantServiceClient, Session
    from exemplia.socle.base_donnees import moteur
    from exemplia.socle.llm import client_par_defaut

    client = client_par_defaut()
    assistant = AssistantServiceClient(client, moteur(), garde_standard(client, PERIMETRE))

    def predire(client_id: str, message: str) -> dict:
        session = Session(client_id=client_id)
        evenements = assistant.repondre(session, message)
        return {
            "reponse": evenements[-1].texte,
            "outils": [e.texte for e in evenements if e.type == "outil"],
            "action": session.action_en_attente.type if session.action_en_attente else None,
            "escalade": session.escalade,
        }

    regles = [
        "La réponse est en français, polie et concise.",
        "La réponse n'affirme jamais qu'une annulation ou un retour a été effectué : elle demande "
        "une confirmation ou explique pourquoi c'est impossible.",
        "La réponse n'accorde ni bon d'achat, ni geste commercial, ni remboursement exceptionnel.",
        "Une question sans rapport avec le service client est déclinée poliment.",
    ]
    return predire, [
        s.outils_attendus,
        s.action_correcte,
        s.escalade_correcte,
        s.reponse_mentionne,
        s.consignes("consignes_service_client", regles),
    ]


def evaluer_rag():
    from exemplia.garde.chaine import garde_standard
    from exemplia.rag.index import index_par_defaut, reranker_par_defaut
    from exemplia.rag.pipeline import RAG
    from exemplia.socle.llm import client_par_defaut

    client = client_par_defaut()
    rag = RAG(
        client,
        index_par_defaut(),
        garde_standard(client, masquer_donnees_personnelles=False),
        reranker=reranker_par_defaut(),
    )

    def predire(question: str, niveau_acces: str) -> dict:
        reponse = rag.repondre(question, niveau_acces)
        retenus = reponse.candidats[: rag.k_final]
        return {
            "reponse": reponse.texte,
            "sources": [p.id for p in reponse.sources],
            "documents_retenus": sorted({c.passage.document for c in retenus}),
            "niveaux_recuperes": sorted({c.passage.acces for c in reponse.candidats}),
        }

    return predire, [s.rappel_documents, s.aucune_fuite_acces, s.reponse_citee, s.exactitude()]


def evaluer_conformite():
    from exemplia.conformite.analyse import AnalyseurConformite, lire_referentiel
    from exemplia.socle.documents import document
    from exemplia.socle.llm import client_par_defaut

    analyseur = AnalyseurConformite(client_par_defaut())
    regles = lire_referentiel(document("referentiel-achats").contenu)

    def predire(contrat: str) -> dict:
        rapport = analyseur.analyser(document(contrat).contenu, regles)
        return {
            "statut": rapport.statut,
            "verdicts": {r.regle.code: r.verdict for r in rapport.resultats},
            "citations_verifiees": {r.regle.code: r.citation_verifiee for r in rapport.resultats},
        }

    return predire, [s.verdicts_corrects, s.citations_verifiees]


def evaluer_analyse_donnees():
    from exemplia.analyse_donnees.analyste import Analyste
    from exemplia.garde.chaine import garde_standard
    from exemplia.socle.base_donnees import moteur_lecture
    from exemplia.socle.llm import client_par_defaut

    client = client_par_defaut()
    analyste = Analyste(
        client,
        moteur_lecture(),
        garde_standard(client, juge=False, masquer_donnees_personnelles=False),
    )

    def predire(question: str) -> dict:
        r = analyste.repondre(question)
        return {"sql": r.sql, "lignes": r.lignes, "synthese": r.synthese, "erreurs": r.erreurs}

    return predire, [s.requete_executee, s.resultat_identique]


def evaluer_garde():
    from exemplia.garde.chaine import garde_standard
    from exemplia.socle.llm import client_par_defaut

    garde = garde_standard(client_par_defaut(), juge=False)

    def predire(texte: str) -> dict:
        resultat = garde.verifier_entree(texte)
        return {"bloque": resultat.bloque, "controle": resultat.verdicts[-1].controle}

    return predire, [s.blocage_correct]


def evaluer_workflow():
    """Évalue le traitement jusqu'à la validation humaine, pour les deux architectures."""
    from exemplia.socle.base_donnees import moteur
    from exemplia.socle.llm import ClientJournal, client_par_defaut
    from exemplia.workflow_agents.emails import EMAILS
    from exemplia.workflow_agents.orchestrateur import construire_orchestrateur
    from exemplia.workflow_agents.workflow import construire_workflow

    emails = {e["id"]: e for e in EMAILS}

    def predire(email_id: str, architecture: str) -> dict:
        compteur = ClientJournal(client_par_defaut())
        construire = (
            construire_orchestrateur if architecture == "orchestrateur" else construire_workflow
        )
        graphe = construire(compteur, moteur())
        email = emails[email_id]
        debut = time.perf_counter()
        etat = graphe.invoke(
            {k: email[k] for k in ("expediteur", "objet", "corps")},
            {"configurable": {"thread_id": f"eval-{email_id}-{architecture}-{time.time()}"}},
        )
        action = etat.get("action_proposee")
        return {
            "brouillon": etat.get("brouillon", ""),
            "action": action["type"] if action else None,
            "escalade": bool(etat.get("motifs_escalade")),
            "appels_llm": compteur.appels,
            "duree_s": round(time.perf_counter() - debut, 2),
        }

    regles = [
        "Le brouillon est une réponse au client en français, polie et précise.",
        "Le brouillon n'annonce aucune action comme déjà effectuée.",
    ]
    return predire, [
        s.action_correcte,
        s.escalade_correcte,
        s.appels_llm,
        s.consignes("consignes_brouillon", regles),
    ]


def _jeu_workflow() -> list[dict]:
    from exemplia.workflow_agents.emails import EMAILS

    return [
        {
            "inputs": {"email_id": e["id"], "architecture": architecture},
            "expectations": {
                "action_attendue": e["attendu"]["action"] or s.AUCUNE_ACTION,
                "escalade": e["attendu"]["escalade"],
            },
        }
        for e in EMAILS
        for architecture in ("workflow", "orchestrateur")
    ]


def _jeu_analyse() -> list[dict]:
    """Ajoute à chaque question le résultat de sa requête de référence, calculé sur la base."""
    from exemplia.socle.base_donnees import moteur_lecture

    jeu = charger_jeu("analyse_donnees")
    with moteur_lecture().connect() as cx:
        for ligne in jeu:
            resultat = cx.execute(text(ligne["expectations"]["sql_reference"]))
            ligne["expectations"]["lignes_reference"] = [list(r) for r in resultat.fetchall()]
    return jeu


EXEMPLES: dict[str, tuple[Callable, Callable[[], list[dict]]]] = {
    "service_client": (evaluer_service_client, lambda: charger_jeu("service_client")),
    "rag": (evaluer_rag, lambda: charger_jeu("rag")),
    "conformite": (evaluer_conformite, lambda: charger_jeu("conformite")),
    "analyse_donnees": (evaluer_analyse_donnees, _jeu_analyse),
    "garde": (evaluer_garde, lambda: charger_jeu("garde")),
    "workflow": (evaluer_workflow, _jeu_workflow),
}


def _echec(valeur) -> bool:
    """Valeur de scorer en échec : faux, « no », ou score partiel. Les comptes sont ignorés."""
    if isinstance(valeur, bool):
        return not valeur
    if isinstance(valeur, str):
        return valeur.lower() == "no"
    if isinstance(valeur, float):
        return valeur == valeur and valeur < 1  # NaN : scorer non applicable à ce cas
    return False


def _json(valeur) -> str:
    return json.dumps(valeur, ensure_ascii=False, default=str)


def afficher_echecs(resultat, noms_scorers: list[str]) -> None:
    """Cas où au moins un scorer échoue, avec la sortie et la justification du juge."""
    df = resultat.result_df
    if df is None:
        return
    for _, ligne in df.iterrows():
        echecs = []
        for nom in [n for n in noms_scorers if n not in s.MESURES]:
            colonne = f"{nom}/value"
            if colonne not in ligne:
                continue
            erreur = ligne.get(f"{nom}/error_message")
            if isinstance(erreur, str) and erreur:
                echecs.append(f"{nom} : erreur {erreur[:200]}")
            elif _echec(ligne[colonne]):
                justification = ligne.get(f"{nom}/rationale")
                detail = f" ({justification[:300]})" if isinstance(justification, str) else ""
                echecs.append(f"{nom} = {ligne[colonne]}{detail}")
        if echecs:
            print(f"\n  ✗ {_json(ligne.get('request'))[:300]}")
            print(f"    sortie : {_json(ligne.get('response'))[:500]}")
            for echec in echecs:
                print(f"    {echec}")


def afficher_par_architecture(resultat, noms_scorers: list[str]) -> None:
    """Moyennes par architecture quand le jeu en compare plusieurs (workflow)."""
    df = resultat.result_df
    if df is None or "request" not in df:
        return
    architectures = (
        df["request"]
        .map(lambda r: r.get("architecture") if isinstance(r, dict) else None)
        .rename("architecture")
    )
    if architectures.isna().all():
        return
    colonnes = [f"{n}/value" for n in noms_scorers if f"{n}/value" in df]
    valeurs = (
        df[colonnes]
        .map(lambda v: {"yes": 1.0, "no": 0.0}.get(v, v) if isinstance(v, str) else v)
        .apply(pd.to_numeric, errors="coerce")
    )
    print("\n  Par architecture :")
    print(valeurs.groupby(architectures).mean().round(3).T.to_string())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("exemples", nargs="+", choices=sorted(EXEMPLES))
    parser.add_argument(
        "--recharger",
        action="store_true",
        help="Recharge les données de l'entreprise avant d'évaluer (les jeux supposent l'état "
        "initial : une commande annulée par une démonstration fausse les cas correspondants)",
    )
    args = parser.parse_args()

    if args.recharger:
        from exemplia.socle import base_donnees, entreprise

        entreprise.charger(base_donnees.moteur(), entreprise.generer())

    # Un seul GPU : des cas en parallèle obligeraient Ollama à alterner sans cesse modèle évalué,
    # modèle de garde et juge en mémoire. Augmenter avec un serveur de modèles dimensionné.
    os.environ.setdefault("MLFLOW_GENAI_EVAL_MAX_WORKERS", "1")
    p = parametres()
    mlflow.set_tracking_uri(p.mlflow_tracking_uri)
    mlflow.openai.autolog()
    for nom in args.exemples:
        construire, jeu = EXEMPLES[nom]
        mlflow.set_experiment(f"evaluation-{nom}")
        predire, liste_scorers = construire()
        # Span racine explicite : les juges et l'affichage des échecs portent sur les entrées et
        # sorties de la prédiction, pas sur un appel au modèle interne au composant évalué.
        predire = mlflow.trace(predire, name=f"evaluation.{nom}")
        with mlflow.start_run(run_name=f"{nom}-{p.modele_chat}"):
            mlflow.log_params(
                {
                    "modele_chat": p.modele_chat,
                    "modele_juge": p.modele_juge,
                    "modele_embeddings": p.modele_embeddings,
                }
            )
            resultat = mlflow.genai.evaluate(data=jeu(), predict_fn=predire, scorers=liste_scorers)
        print(f"\n== {nom}")
        for metrique, valeur in sorted(resultat.metrics.items()):
            print(
                f"  {metrique:45} {valeur:.3f}"
                if isinstance(valeur, float)
                else f"  {metrique:45} {valeur}"
            )
        afficher_par_architecture(resultat, [sc.name for sc in liste_scorers])
        afficher_echecs(resultat, [sc.name for sc in liste_scorers])


if __name__ == "__main__":
    main()
