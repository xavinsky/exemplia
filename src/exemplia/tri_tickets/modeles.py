"""Les approches de classification des tickets, sous une interface commune `predire(textes)`.

Les modèles qui dépendent d'un serveur (embeddings, LLM) sont des modèles pyfunc MLflow : une fois
enregistrés, ils se chargent et s'appellent comme le modèle scikit-learn.
"""

from __future__ import annotations

from typing import Literal

import mlflow.pyfunc
from pydantic import BaseModel
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from exemplia.garde.prompts import delimiter
from exemplia.socle.entreprise import CATEGORIES_TICKETS
from exemplia.socle.llm import ClientLLM, client_par_defaut

NOM_PROMPT = "tri-tickets-zero-shot"
PROMPT_ZERO_SHOT = """Classe la demande client dans une seule catégorie :
- livraison : suivi, retard, adresse, colis non reçu ;
- retour : renvoi, échange, remboursement d'un retour ;
- facturation : prélèvement, facture, moyen de paiement, abonnement facturé ;
- compte : connexion, mot de passe, données personnelles, préférences ;
- produit : caractéristiques, compatibilité, disponibilité, panne, garantie.

{{ticket}}"""


class Categorie(BaseModel):
    categorie: Literal["livraison", "retour", "facturation", "compte", "produit"]


def _textes(model_input) -> list[str]:
    if hasattr(model_input, "iloc"):
        return model_input.iloc[:, 0].astype(str).tolist()
    return [str(t) for t in model_input]


def pipeline_tfidf(c: float = 5.0) -> Pipeline:
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)),
            ("regression", LogisticRegression(C=c, max_iter=2000)),
        ]
    )


class ClassifieurEmbeddings(mlflow.pyfunc.PythonModel):
    """Embeddings du serveur de modèles + régression logistique entraînée localement."""

    def __init__(self, modele_embeddings: str, c: float = 5.0) -> None:
        self.modele_embeddings = modele_embeddings
        self.regression = LogisticRegression(C=c, max_iter=2000)
        self.client: ClientLLM | None = None

    def entrainer(self, textes: list[str], etiquettes: list[str]) -> ClassifieurEmbeddings:
        self.regression.fit(self._vecteurs(textes), etiquettes)
        return self

    def _vecteurs(self, textes):
        client = self.client or client_par_defaut()
        return client.vectoriser(textes, modele=self.modele_embeddings)

    def predict(self, context, model_input: list[str], params=None) -> list[str]:
        return self.regression.predict(self._vecteurs(_textes(model_input))).tolist()

    def __getstate__(self):
        # Le client (connexion réseau) n'est pas sérialisé avec le modèle.
        return {**self.__dict__, "client": None}


class ClassifieurLLM(mlflow.pyfunc.PythonModel):
    """Classification sans exemple par le LLM, avec un prompt versionné dans MLflow."""

    def __init__(self, modele: str, prompt_uri: str | None = None) -> None:
        self.modele = modele
        self.prompt_uri = prompt_uri
        self.client: ClientLLM | None = None
        self._gabarit: str | None = None

    def _prompt(self, ticket: str) -> str:
        if self._gabarit is None:
            self._gabarit = (
                mlflow.genai.load_prompt(self.prompt_uri).template
                if self.prompt_uri
                else PROMPT_ZERO_SHOT
            )
        return self._gabarit.replace("{{ticket}}", delimiter("ticket", ticket))

    def predict(self, context, model_input: list[str], params=None) -> list[str]:
        client = self.client or client_par_defaut()
        return [
            client.extraire(
                [{"role": "user", "content": self._prompt(t)}], Categorie, modele=self.modele
            ).categorie
            for t in _textes(model_input)
        ]

    def __getstate__(self):
        return {**self.__dict__, "client": None, "_gabarit": None}


__all__ = [
    "CATEGORIES_TICKETS",
    "ClassifieurEmbeddings",
    "ClassifieurLLM",
    "NOM_PROMPT",
    "PROMPT_ZERO_SHOT",
    "pipeline_tfidf",
]
