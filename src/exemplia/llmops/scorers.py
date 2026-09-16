"""Scorers d'évaluation : déterministes (code) et LLM juges.

Les scorers déterministes sont gratuits, rapides et reproductibles : ils vérifient tout ce qui peut
l'être par du code (outil appelé, action proposée, document récupéré, résultat SQL). Les juges LLM
évaluent ce que le code ne sait pas mesurer (exactitude des faits, ton, respect des consignes).
"""

from __future__ import annotations

from decimal import Decimal

from mlflow.genai.scorers import Correctness, Guidelines, scorer

from exemplia.socle.config import parametres


def uri_juge() -> str:
    """Modèle juge au format MLflow (`fournisseur:/modele`)."""
    p = parametres()
    return f"{'ollama' if p.serveur_est_ollama else 'openai'}:/{p.modele_juge}"


def parametres_juge() -> dict | None:
    """Options d'inférence des juges : les mêmes que pour le reste du projet.

    Les juges de MLflow qui les transmettent au serveur de modèles évitent ainsi de payer la
    réflexion du modèle juge sur chaque cas évalué.
    """
    reflexion = parametres().llm_reflexion
    return {"reasoning_effort": reflexion} if reflexion else None


def exactitude(model: str | None = None):
    return Correctness(model=model or uri_juge(), inference_params=parametres_juge())


def consignes(nom: str, regles: list[str], model: str | None = None):
    return Guidelines(
        name=nom,
        guidelines=regles,
        model=model or uri_juge(),
        inference_params=parametres_juge(),
    )


# --- Service client ------------------------------------------------------------------------------


@scorer
def outils_attendus(outputs: dict, expectations: dict) -> bool | None:
    """Chaque outil attendu a été appelé (`a|b` : l'un ou l'autre suffit)."""
    if "outils_attendus" not in expectations:
        return None
    appeles = set(outputs["outils"])
    if not expectations["outils_attendus"]:
        return not appeles
    return all(set(attendu.split("|")) & appeles for attendu in expectations["outils_attendus"])


# MLflow n'accepte pas d'attente de valeur nulle : l'absence d'action s'écrit « aucune ».
AUCUNE_ACTION = "aucune"


@scorer
def reponse_mentionne(outputs: dict, expectations: dict) -> bool | None:
    """La réponse cite ce qu'elle doit citer : référence de commande, montant, délai."""
    attendus = expectations.get("mentions")
    if not attendus:
        return None
    return all(mention.lower() in outputs["reponse"].lower() for mention in attendus)


@scorer
def action_correcte(outputs: dict, expectations: dict) -> bool | None:
    if "action_attendue" not in expectations:
        return None
    return (outputs.get("action") or AUCUNE_ACTION) == expectations["action_attendue"]


@scorer
def escalade_correcte(outputs: dict, expectations: dict) -> bool | None:
    if "escalade" not in expectations:
        return None
    return bool(outputs.get("escalade")) == expectations["escalade"]


# --- RAG -----------------------------------------------------------------------------------------


@scorer
def rappel_documents(outputs: dict, expectations: dict) -> float | None:
    """Part des documents attendus présents dans les passages retenus pour la génération."""
    attendus = set(expectations.get("documents_attendus", []))
    if not attendus:
        return None
    return len(attendus & set(outputs["documents_retenus"])) / len(attendus)


@scorer
def aucune_fuite_acces(inputs: dict, outputs: dict) -> bool:
    """Aucun passage d'un niveau d'accès supérieur à celui de l'utilisateur n'a été récupéré."""
    from exemplia.rag.index import niveaux_autorises

    return set(outputs["niveaux_recuperes"]) <= set(niveaux_autorises(inputs["niveau_acces"]))


@scorer
def reponse_citee(outputs: dict, expectations: dict) -> bool:
    """Une réponse informative cite au moins une source ; une non-réponse n'en cite pas."""
    if expectations.get("reponse_inconnue"):
        return not outputs["sources"]
    return bool(outputs["sources"])


# --- Conformité ------------------------------------------------------------------------------------


@scorer
def verdicts_corrects(outputs: dict, expectations: dict) -> float:
    attendus = expectations["verdicts"]
    justes = sum(outputs["verdicts"].get(code) in acceptes for code, acceptes in attendus.items())
    return justes / len(attendus)


@scorer
def citations_verifiees(outputs: dict) -> float:
    return sum(outputs["citations_verifiees"].values()) / max(
        len(outputs["citations_verifiees"]), 1
    )


# --- Analyse de données ----------------------------------------------------------------------------


def normaliser_lignes(lignes: list[list]) -> list[tuple]:
    """Valeurs comparables quel que soit l'ordre des lignes, des colonnes et le type numérique."""

    def valeur(v):
        if isinstance(v, (int, float, Decimal)):
            return f"{float(v):.2f}"
        return str(v).strip().lower()

    return sorted(tuple(sorted(valeur(v) for v in ligne)) for ligne in lignes)


@scorer
def resultat_identique(outputs: dict, expectations: dict) -> bool:
    return normaliser_lignes(outputs["lignes"]) == normaliser_lignes(
        expectations["lignes_reference"]
    )


@scorer
def requete_executee(outputs: dict) -> bool:
    return bool(outputs["sql"])


# --- Garde -----------------------------------------------------------------------------------------


@scorer
def blocage_correct(outputs: dict, expectations: dict) -> bool:
    return outputs["bloque"] == expectations["bloque"]


# --- Workflow ----------------------------------------------------------------------------------------


@scorer
def appels_llm(outputs: dict) -> int:
    return outputs["appels_llm"]


# Mesures qui ne sont ni réussies ni échouées (affichées sans jugement).
MESURES = {"appels_llm"}
