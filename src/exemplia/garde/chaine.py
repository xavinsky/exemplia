"""Chaîne de garde : applique les contrôles dans l'ordre et s'arrête au premier blocage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import mlflow
from mlflow.entities import SpanType

from exemplia.garde.controles import (
    ENTITES_SENSIBLES,
    Controle,
    ControleDonneesPersonnelles,
    ControleFuitePrompt,
    ControleInjection,
    ControleLongueur,
    ControleModeration,
    Decision,
    JugeLLM,
    Verdict,
    classifieur_transformers,
)
from exemplia.socle.config import parametres
from exemplia.socle.llm import ClientLLM

MESSAGE_BLOCAGE_ENTREE = (
    "Je ne peux pas traiter cette demande. Vous pouvez la reformuler ou demander à parler à un "
    "conseiller."
)
MESSAGE_BLOCAGE_SORTIE = (
    "Je préfère ne pas répondre de façon incertaine. Un conseiller peut prendre le relais."
)


@dataclass
class ResultatGarde:
    decision: Decision
    texte: str
    verdicts: list[Verdict] = field(default_factory=list)

    @property
    def bloque(self) -> bool:
        return self.decision == Decision.BLOQUER

    @property
    def raison(self) -> str:
        return next((v.raison for v in self.verdicts if v.decision == Decision.BLOQUER), "")


class Garde:
    def __init__(
        self,
        entree: list[Controle] | None = None,
        sortie: list[Controle] | None = None,
    ) -> None:
        self.entree = entree or []
        self.sortie = sortie or []

    def verifier_entree(self, texte: str, contexte: dict[str, Any] | None = None) -> ResultatGarde:
        return self._appliquer("entree", self.entree, texte, contexte or {})

    def verifier_sortie(self, texte: str, contexte: dict[str, Any] | None = None) -> ResultatGarde:
        return self._appliquer("sortie", self.sortie, texte, contexte or {})

    def _appliquer(self, sens, controles, texte, contexte) -> ResultatGarde:
        verdicts: list[Verdict] = []
        decision = Decision.AUTORISER
        for controle in controles:
            with mlflow.start_span(
                name=f"garde.{sens}.{controle.nom}", span_type=SpanType.GUARDRAIL
            ) as span:
                span.set_inputs({"texte": texte})
                verdict = controle.verifier(texte, contexte)
                span.set_outputs(
                    {
                        "decision": verdict.decision.value,
                        "raison": verdict.raison,
                        **verdict.details,
                    }
                )
            verdicts.append(verdict)
            if verdict.decision == Decision.BLOQUER:
                return ResultatGarde(Decision.BLOQUER, texte, verdicts)
            if verdict.decision == Decision.MODIFIER and verdict.texte is not None:
                texte = verdict.texte
                decision = Decision.MODIFIER
        return ResultatGarde(decision, texte, verdicts)


def garde_standard(
    client: ClientLLM | None = None,
    perimetre: str = "",
    moderation: bool = True,
    juge: bool = True,
    masquer_donnees_personnelles: bool = True,
) -> Garde:
    """Configuration de référence utilisée par les exemples.

    Sans client, seuls les contrôles sans modèle sont actifs (utile en test ou sans GPU).
    """
    p = parametres()
    classifieur = (
        classifieur_transformers(p.classifieur_injection) if p.classifieur_injection else None
    )
    entree: list[Controle] = [
        ControleLongueur(),
        ControleInjection(
            classifieur=classifieur,
            seuil=p.classifieur_injection_seuil,
            bloquer_classifieur=p.classifieur_injection_bloque,
        ),
    ]
    if masquer_donnees_personnelles:
        entree.append(ControleDonneesPersonnelles())
    sortie: list[Controle] = [
        ControleFuitePrompt(),
        ControleDonneesPersonnelles(entites=ENTITES_SENSIBLES, bloquer=True),
    ]
    if client is not None and moderation:
        entree.append(ControleModeration(client))
    if client is not None and juge:
        sortie.append(JugeLLM(client, perimetre=perimetre))
    return Garde(entree, sortie)
