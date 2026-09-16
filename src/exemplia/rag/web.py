"""Interface du RAG documentaire."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request

from exemplia.garde.chaine import garde_standard
from exemplia.rag.index import IndexHybride, Reranker, index_par_defaut, reranker_par_defaut
from exemplia.rag.pipeline import RAG
from exemplia.socle.documents import NIVEAUX_ACCES, charger_documents
from exemplia.socle.llm import ClientLLM
from exemplia.socle.web import dep_client_llm, gabarits, mesurer

routeur = APIRouter(prefix="/rag")

QUESTIONS = [
    ("public", "Combien de temps ai-je pour retourner un produit ?"),
    ("public", "Les abonnements sont-ils remboursables ?"),
    ("interne", "Jusqu'à quel montant un conseiller peut-il accorder un geste commercial ?"),
    ("confidentiel", "Quel est le délai de paiement du contrat avec Fournisseur Beta ?"),
    ("public", "Quel est le chiffre d'affaires de l'entreprise ?"),
]


def dep_index() -> IndexHybride:
    return index_par_defaut()


def dep_reranker() -> Reranker:
    return reranker_par_defaut()


@routeur.get("")
def page(request: Request):
    return gabarits().TemplateResponse(
        request,
        "rag/index.html",
        {
            "actif": "rag",
            "niveaux": NIVEAUX_ACCES,
            "questions": QUESTIONS,
            "documents": charger_documents(),
        },
    )


@routeur.post("/question")
def question(
    request: Request,
    client_llm: Annotated[ClientLLM, Depends(dep_client_llm)],
    index: Annotated[IndexHybride, Depends(dep_index)],
    question: Annotated[str, Form()],
    niveau_acces: Annotated[str, Form()] = "public",
    rerank: Annotated[bool, Form()] = False,
):
    with mesurer(client_llm) as (client, mesure):
        garde = garde_standard(
            client,
            perimetre="documents internes d'Entreprise Exemple",
            masquer_donnees_personnelles=False,
        )
        # Même index, mais le client compté : l'embedding de la question entre dans la mesure.
        index_mesure = IndexHybride(index.qdrant, client, index.sparse, index.collection)
        rag = RAG(client, index_mesure, garde, reranker=dep_reranker() if rerank else None)
        reponse = rag.repondre(question, niveau_acces)
    return gabarits().TemplateResponse(
        request, "rag/reponse.html", {"reponse": reponse, "mesure": mesure}
    )
