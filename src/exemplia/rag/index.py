"""Index hybride Qdrant : vecteurs denses (sens) + BM25 (mots exacts), fusionnés par RRF.

Le dense retrouve « délai pour renvoyer un article » quand le document dit « retourner un
produit » ; le BM25 retrouve les références exactes (« R5 », « article 28 ») que le dense rate.
Le filtre d'accès est appliqué dans la requête Qdrant : un passage non autorisé n'est jamais
récupéré, donc jamais envoyé au LLM.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections import Counter
from functools import lru_cache
from typing import Protocol

import mlflow
from mlflow.entities import SpanType
from qdrant_client import QdrantClient
from qdrant_client import models as qm

from exemplia.rag.decoupage import Passage
from exemplia.socle.documents import NIVEAUX_ACCES
from exemplia.socle.llm import ClientLLM

COLLECTION = "documents_entreprise"


class EncodeurSparse(Protocol):
    def documents(self, textes: list[str]) -> list[qm.SparseVector]: ...
    def requete(self, texte: str) -> qm.SparseVector: ...


class Bm25Fastembed:
    """BM25 avec racinisation française (fastembed, CPU). Les poids IDF sont calculés par Qdrant."""

    def __init__(self) -> None:
        from fastembed import SparseTextEmbedding

        self._modele = SparseTextEmbedding("Qdrant/bm25", language="french")

    def documents(self, textes):
        return [
            qm.SparseVector(indices=e.indices.tolist(), values=e.values.tolist())
            for e in self._modele.embed(textes)
        ]

    def requete(self, texte):
        e = next(iter(self._modele.query_embed(texte)))
        return qm.SparseVector(indices=e.indices.tolist(), values=e.values.tolist())


class FauxBm25:
    """Fréquence des mots hachés : suffisant pour tester la plomberie sans modèle."""

    @staticmethod
    def _vecteur(texte: str) -> qm.SparseVector:
        compte = Counter(
            int(hashlib.md5(m.encode()).hexdigest()[:8], 16)
            for m in re.findall(r"\w+", texte.lower())
        )
        return qm.SparseVector(indices=list(compte), values=[float(v) for v in compte.values()])

    def documents(self, textes):
        return [self._vecteur(t) for t in textes]

    def requete(self, texte):
        return self._vecteur(texte)


def niveaux_autorises(niveau_utilisateur: str) -> list[str]:
    return NIVEAUX_ACCES[: NIVEAUX_ACCES.index(niveau_utilisateur) + 1]


class IndexHybride:
    def __init__(
        self,
        qdrant: QdrantClient,
        client_llm: ClientLLM,
        sparse: EncodeurSparse,
        collection: str = COLLECTION,
    ) -> None:
        self.qdrant = qdrant
        self.llm = client_llm
        self.sparse = sparse
        self.collection = collection

    @staticmethod
    def _identifiant(passage: Passage) -> str:
        """Identifiant de point stable, dérivé de celui du passage : réindexer ne duplique pas."""
        return str(uuid.uuid5(uuid.NAMESPACE_URL, passage.id))

    def _creer_collection(self, dimension: int) -> None:
        self.qdrant.create_collection(
            self.collection,
            vectors_config={"dense": qm.VectorParams(size=dimension, distance=qm.Distance.COSINE)},
            sparse_vectors_config={"bm25": qm.SparseVectorParams(modifier=qm.Modifier.IDF)},
        )
        self.qdrant.create_payload_index(self.collection, "acces", qm.PayloadSchemaType.KEYWORD)

    def _envoyer(self, passages: list[Passage]) -> None:
        textes = [p.texte_indexe for p in passages]
        denses = self.llm.vectoriser(textes)
        sparses = self.sparse.documents(textes)
        if not self.qdrant.collection_exists(self.collection):
            self._creer_collection(len(denses[0]))
        self.qdrant.upsert(
            self.collection,
            [
                qm.PointStruct(
                    id=self._identifiant(p),
                    vector={"dense": d, "bm25": s},
                    payload=p.__dict__,
                )
                for p, d, s in zip(passages, denses, sparses, strict=True)
            ],
        )

    def indexer(self, passages: list[Passage]) -> int:
        """Reconstruit l'index à partir de zéro."""
        if self.qdrant.collection_exists(self.collection):
            self.qdrant.delete_collection(self.collection)
        self._envoyer(passages)
        return len(passages)

    def synchroniser(self, passages: list[Passage]) -> dict[str, int]:
        """Met l'index à jour sans le reconstruire : seuls les passages nouveaux ou modifiés sont
        vectorisés, et ceux qui ont disparu des documents sont supprimés.

        Sur une grande base, c'est la différence entre quelques secondes et une réindexation
        complète à chaque modification d'un document.
        """
        if not self.qdrant.collection_exists(self.collection):
            return {"ajoutes": self.indexer(passages), "inchanges": 0, "supprimes": 0}
        champs = ("titre_document", "section", "texte")
        connus: dict[str, tuple] = {}
        suivant = None
        while True:
            points, suivant = self.qdrant.scroll(
                self.collection, limit=256, offset=suivant, with_payload=list(champs)
            )
            connus.update({str(p.id): tuple(p.payload.get(c) for c in champs) for p in points})
            if suivant is None:
                break
        a_envoyer = [
            p
            for p in passages
            if connus.get(self._identifiant(p)) != tuple(getattr(p, c) for c in champs)
        ]
        if a_envoyer:
            self._envoyer(a_envoyer)
        obsoletes = set(connus) - {self._identifiant(p) for p in passages}
        if obsoletes:
            self.qdrant.delete(self.collection, points_selector=list(obsoletes))
        return {
            "ajoutes": len(a_envoyer),
            "inchanges": len(passages) - len(a_envoyer),
            "supprimes": len(obsoletes),
        }

    @mlflow.trace(name="rag.recherche_hybride", span_type=SpanType.RETRIEVER)
    def rechercher(
        self, question: str, niveau_acces: str, k: int = 20
    ) -> list[tuple[Passage, float]]:
        filtre = qm.Filter(
            must=[
                qm.FieldCondition(
                    key="acces", match=qm.MatchAny(any=niveaux_autorises(niveau_acces))
                )
            ]
        )
        dense = self.llm.vectoriser([question])[0]
        resultat = self.qdrant.query_points(
            self.collection,
            prefetch=[
                qm.Prefetch(query=dense, using="dense", limit=k, filter=filtre),
                qm.Prefetch(
                    query=self.sparse.requete(question), using="bm25", limit=k, filter=filtre
                ),
            ],
            query=qm.FusionQuery(fusion=qm.Fusion.RRF),
            limit=k,
        )
        return [(Passage(**p.payload), p.score) for p in resultat.points]


class Reranker(Protocol):
    def scorer(self, question: str, textes: list[str]) -> list[float]: ...


class RerankerFastembed:
    """Cross-encoder multilingue : lit question et passage ensemble, plus précis que la fusion."""

    def __init__(self, modele: str = "jinaai/jina-reranker-v2-base-multilingual") -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self._modele = TextCrossEncoder(modele)

    def scorer(self, question, textes):
        return [float(s) for s in self._modele.rerank(question, textes)]


@lru_cache
def index_par_defaut() -> IndexHybride:
    from exemplia.socle.config import parametres
    from exemplia.socle.llm import client_par_defaut

    return IndexHybride(
        QdrantClient(url=parametres().qdrant_url), client_par_defaut(), Bm25Fastembed()
    )


@lru_cache
def reranker_par_defaut() -> Reranker:
    return RerankerFastembed()
