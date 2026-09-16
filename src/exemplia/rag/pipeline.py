"""Pipeline RAG : garde, recherche hybride, reranking, génération citée, garde de sortie."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import mlflow
from mlflow.entities import SpanType

from exemplia.garde.chaine import MESSAGE_BLOCAGE_ENTREE, MESSAGE_BLOCAGE_SORTIE, Garde
from exemplia.garde.controles import Verdict
from exemplia.garde.prompts import CONSIGNE_CONTENU_NON_FIABLE, delimiter
from exemplia.rag.decoupage import Passage
from exemplia.rag.index import IndexHybride, Reranker
from exemplia.socle import tracage
from exemplia.socle.llm import ClientLLM

REPONSE_INCONNUE = "Je ne trouve pas cette information dans les documents auxquels vous avez accès."

PROMPT_SYSTEME = f"""Tu réponds aux questions des collaborateurs d'Entreprise Exemple à partir des
sources fournies, et uniquement d'elles.

- Chaque affirmation est suivie du numéro de sa source entre crochets, par exemple [2].
- Si les sources ne permettent pas de répondre, réponds exactement : « {REPONSE_INCONNUE} »
- N'utilise pas tes connaissances générales, même si tu penses connaître la réponse.
- Réponds en français, de façon concise.

{CONSIGNE_CONTENU_NON_FIABLE}"""


# Le contrôle de fuite ne compare pas la réponse à la phrase de non-réponse imposée par le prompt :
# la reprendre mot pour mot est le comportement attendu.
CONSIGNES_SANS_NON_REPONSE = PROMPT_SYSTEME.replace(REPONSE_INCONNUE, "")


@dataclass
class Candidat:
    passage: Passage
    score_fusion: float
    score_rerank: float | None = None


@dataclass
class ReponseRAG:
    texte: str
    sources: list[Passage] = field(default_factory=list)
    candidats: list[Candidat] = field(default_factory=list)
    verdicts: list[Verdict] = field(default_factory=list)
    bloquee: bool = False


class RAG:
    def __init__(
        self,
        client_llm: ClientLLM,
        index: IndexHybride,
        garde: Garde,
        reranker: Reranker | None = None,
        k_recherche: int = 20,
        k_final: int = 5,
        seuil_rerank: float | None = None,
    ) -> None:
        self.llm = client_llm
        self.index = index
        self.garde = garde
        self.reranker = reranker
        self.k_recherche = k_recherche
        self.k_final = k_final
        self.seuil_rerank = seuil_rerank

    @mlflow.trace(name="rag.repondre", span_type=SpanType.CHAIN)
    def repondre(self, question: str, niveau_acces: str = "public") -> ReponseRAG:
        tracage.decrire_trace(tags={"exemple": "rag", "niveau_acces": niveau_acces})
        entree = self.garde.verifier_entree(question)
        if entree.bloque:
            return ReponseRAG(MESSAGE_BLOCAGE_ENTREE, verdicts=entree.verdicts, bloquee=True)

        candidats = self.selectionner(entree.texte, niveau_acces)
        retenus = candidats[: self.k_final]
        if not retenus:
            return ReponseRAG(REPONSE_INCONNUE, candidats=candidats, verdicts=entree.verdicts)

        sources = "\n\n".join(
            delimiter("source", c.passage.texte_indexe, numero=str(i))
            for i, c in enumerate(retenus, start=1)
        )
        reponse = self.llm.discuter(
            [
                {"role": "system", "content": PROMPT_SYSTEME},
                {"role": "user", "content": f"{sources}\n\nQuestion : {entree.texte}"},
            ]
        )
        texte, cites = _nettoyer_citations(reponse.texte, len(retenus))

        sortie = self.garde.verifier_sortie(
            texte,
            {
                "question": entree.texte,
                "sources": [c.passage.texte for c in retenus],
                "prompt_systeme": CONSIGNES_SANS_NON_REPONSE,
            },
        )
        verdicts = entree.verdicts + sortie.verdicts
        if sortie.bloque:
            return ReponseRAG(
                MESSAGE_BLOCAGE_SORTIE, candidats=candidats, verdicts=verdicts, bloquee=True
            )
        return ReponseRAG(
            texte,
            sources=[retenus[i - 1].passage for i in cites],
            candidats=candidats,
            verdicts=verdicts,
        )

    def selectionner(self, question: str, niveau_acces: str) -> list[Candidat]:
        candidats = [
            Candidat(p, s)
            for p, s in self.index.rechercher(question, niveau_acces, self.k_recherche)
        ]
        if self.reranker is None or not candidats:
            return candidats
        with mlflow.start_span(name="rag.rerank", span_type=SpanType.RERANKER) as span:
            scores = self.reranker.scorer(question, [c.passage.texte_indexe for c in candidats])
            for candidat, score in zip(candidats, scores, strict=True):
                candidat.score_rerank = score
            candidats.sort(key=lambda c: c.score_rerank, reverse=True)
            if self.seuil_rerank is not None:
                candidats = [c for c in candidats if c.score_rerank >= self.seuil_rerank]
            span.set_outputs({"retenus": [c.passage.id for c in candidats[: self.k_final]]})
        return candidats


def _nettoyer_citations(texte: str, nb_sources: int) -> tuple[str, list[int]]:
    """Retire les citations vers des sources inexistantes et renvoie les numéros valides cités."""
    cites: list[int] = []

    def remplacer(m: re.Match) -> str:
        numeros = [int(n) for n in re.findall(r"\d+", m.group(0))]
        valides = [n for n in numeros if 1 <= n <= nb_sources]
        cites.extend(n for n in valides if n not in cites)
        return "".join(f"[{n}]" for n in valides)

    texte = re.sub(r"\[\d+(?:\s*,\s*\d+)*\]", remplacer, texte)
    return texte, sorted(cites)
