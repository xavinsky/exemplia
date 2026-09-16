"""Client LLM commun à tous les exemples.

Les messages suivent le format de l'API Chat Completions d'OpenAI (dictionnaires `role` /
`content`), servi à l'identique par Ollama et vLLM. Le reste du code ne dépend que du protocole
`ClientLLM` : on peut donc injecter `FauxClientLLM` dans les tests.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Protocol, TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from exemplia.socle.config import parametres

M = TypeVar("M", bound=BaseModel)

# Ollama renvoie la réflexion dans un champ séparé ; certains serveurs la laissent dans le contenu.
_BALISE_REFLEXION = re.compile(r"<think>.*?</think>", re.DOTALL)


class ErreurLLM(RuntimeError):
    pass


@dataclass
class AppelOutil:
    id: str
    nom: str
    arguments: dict[str, Any]


@dataclass
class ReponseLLM:
    texte: str = ""
    appels_outils: list[AppelOutil] = field(default_factory=list)

    def message(self) -> dict[str, Any]:
        """Message assistant à réinjecter dans l'historique de conversation."""
        msg: dict[str, Any] = {"role": "assistant", "content": self.texte}
        if self.appels_outils:
            msg["tool_calls"] = [
                {
                    "id": a.id,
                    "type": "function",
                    "function": {"name": a.nom, "arguments": json.dumps(a.arguments)},
                }
                for a in self.appels_outils
            ]
        return msg


def message_outil(appel: AppelOutil, resultat: Any) -> dict[str, Any]:
    contenu = resultat if isinstance(resultat, str) else json.dumps(resultat, default=str)
    return {"role": "tool", "tool_call_id": appel.id, "content": contenu}


def definition_outil(nom: str, description: str, parametres_schema: type[BaseModel]) -> dict:
    """Définition d'outil au format OpenAI, à partir d'un modèle Pydantic des arguments."""
    return {
        "type": "function",
        "function": {
            "name": nom,
            "description": description,
            "parameters": parametres_schema.model_json_schema(),
        },
    }


class ClientLLM(Protocol):
    def discuter(
        self,
        messages: list[dict[str, Any]],
        outils: list[dict] | None = None,
        temperature: float = 0.0,
        modele: str | None = None,
    ) -> ReponseLLM: ...

    def extraire(
        self,
        messages: list[dict[str, Any]],
        schema: type[M],
        temperature: float = 0.0,
        modele: str | None = None,
    ) -> M: ...

    def vectoriser(self, textes: list[str], modele: str | None = None) -> list[list[float]]: ...


class ClientOpenAICompatible:
    """Client pour tout serveur exposant l'API OpenAI (Ollama, vLLM, passerelles)."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        modele: str | None = None,
        modele_embeddings: str | None = None,
        reflexion: str | None = None,
    ) -> None:
        p = parametres()
        self._client = OpenAI(
            base_url=base_url or p.llm_base_url,
            api_key=api_key or p.llm_api_key,
            timeout=p.llm_timeout_s,
        )
        self.modele = modele or p.modele_chat
        self.modele_embeddings = modele_embeddings or p.modele_embeddings
        self.reflexion = reflexion if reflexion is not None else p.llm_reflexion

    def _options(self) -> dict[str, Any]:
        return {"reasoning_effort": self.reflexion} if self.reflexion else {}

    def discuter(self, messages, outils=None, temperature=0.0, modele=None) -> ReponseLLM:
        kwargs = self._options()
        if outils:
            kwargs["tools"] = outils
        reponse = self._client.chat.completions.create(
            model=modele or self.modele, messages=messages, temperature=temperature, **kwargs
        )
        choix = reponse.choices[0].message
        appels = []
        for tc in choix.tool_calls or []:
            try:
                arguments = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {"_brut": tc.function.arguments}
            appels.append(AppelOutil(id=tc.id, nom=tc.function.name, arguments=arguments))
        texte = _BALISE_REFLEXION.sub("", choix.content or "").strip()
        return ReponseLLM(texte=texte, appels_outils=appels)

    def extraire(self, messages, schema, temperature=0.0, modele=None):
        """Sortie structurée validée par Pydantic, avec une nouvelle tentative en cas d'échec."""
        format_reponse = {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()},
        }
        historique = list(messages)
        for tentative in range(2):
            reponse = self._client.chat.completions.create(
                model=modele or self.modele,
                messages=historique,
                temperature=temperature,
                response_format=format_reponse,
                **self._options(),
            )
            texte = _BALISE_REFLEXION.sub("", reponse.choices[0].message.content or "").strip()
            try:
                return schema.model_validate_json(texte)
            except ValidationError as erreur:
                if tentative == 1:
                    raise ErreurLLM(f"Sortie invalide pour {schema.__name__}: {erreur}") from erreur
                historique += [
                    {"role": "assistant", "content": texte},
                    {
                        "role": "user",
                        "content": f"Réponse invalide : {erreur}. Renvoie uniquement un JSON "
                        "conforme au schéma.",
                    },
                ]
        raise AssertionError("inatteignable")

    def vectoriser(self, textes, modele=None) -> list[list[float]]:
        reponse = self._client.embeddings.create(
            model=modele or self.modele_embeddings, input=textes
        )
        return [d.embedding for d in reponse.data]


Scenario = ReponseLLM | str | BaseModel | Callable[[list[dict], list[dict] | None], Any]


class FauxClientLLM:
    """Client scripté pour les tests : renvoie les réponses prévues, dans l'ordre.

    Chaque élément du scénario est une `ReponseLLM`, un texte, une instance Pydantic (pour
    `extraire`) ou une fonction `(messages, outils) -> réponse` pour les cas dynamiques.
    """

    def __init__(self, scenario: list[Scenario] | None = None, dimension: int = 32) -> None:
        self.scenario = list(scenario or [])
        self.dimension = dimension
        self.appels: list[dict[str, Any]] = []

    def _suivant(self, messages, outils):
        self.appels.append({"messages": list(messages), "outils": outils})
        if not self.scenario:
            raise ErreurLLM("FauxClientLLM : scénario épuisé")
        element = self.scenario.pop(0)
        return element(messages, outils) if callable(element) else element

    def discuter(self, messages, outils=None, temperature=0.0, modele=None) -> ReponseLLM:
        element = self._suivant(messages, outils)
        return ReponseLLM(texte=element) if isinstance(element, str) else element

    def extraire(self, messages, schema, temperature=0.0, modele=None):
        element = self._suivant(messages, None)
        if isinstance(element, schema):
            return element
        if isinstance(element, dict):
            return schema.model_validate(element)
        return schema.model_validate_json(element)

    def vectoriser(self, textes, modele=None) -> list[list[float]]:
        """Vecteurs déterministes : textes partageant des mots = vecteurs proches."""
        vecteurs = []
        for texte in textes:
            v = [0.0] * self.dimension
            for mot in re.findall(r"\w+", texte.lower()):
                h = int(hashlib.md5(mot.encode()).hexdigest(), 16)
                v[h % self.dimension] += 1.0
            norme = sum(x * x for x in v) ** 0.5 or 1.0
            vecteurs.append([x / norme for x in v])
        return vecteurs


@dataclass
class Echange:
    """Un appel au modèle, tel qu'il s'affiche dans la trace d'une requête."""

    modele: str
    messages: list[dict[str, Any]]
    reponse: str
    outils: list[str] = field(default_factory=list)


class ClientJournal:
    """Enveloppe d'un client LLM qui compte les appels et retient les échanges.

    Sert à comparer deux architectures (voir le workflow d'agents), à afficher le coût d'une
    réponse et à montrer dans l'interface ce qui a réellement été envoyé au modèle.
    """

    def __init__(self, client: ClientLLM, modele: str = "") -> None:
        self.client = client
        self.modele = modele or getattr(client, "modele", "")
        self.appels = 0
        self.appels_embeddings = 0
        self.echanges: list[Echange] = []

    def _noter(self, messages, reponse, modele, outils=None) -> None:
        self.appels += 1
        self.echanges.append(
            Echange(
                modele=modele or self.modele,
                messages=[dict(m) for m in messages],
                reponse=reponse,
                outils=[o["function"]["name"] for o in outils or []],
            )
        )

    def discuter(self, messages, outils=None, temperature=0.0, modele=None) -> ReponseLLM:
        reponse = self.client.discuter(messages, outils, temperature, modele)
        appels = ", ".join(
            f"{a.nom}({json.dumps(a.arguments, ensure_ascii=False)})" for a in reponse.appels_outils
        )
        self._noter(messages, reponse.texte or appels, modele, outils)
        return reponse

    def extraire(self, messages, schema, temperature=0.0, modele=None):
        resultat = self.client.extraire(messages, schema, temperature, modele)
        self._noter(messages, resultat.model_dump_json(indent=2), modele)
        return resultat

    def vectoriser(self, textes, modele=None) -> list[list[float]]:
        self.appels_embeddings += 1
        return self.client.vectoriser(textes, modele)


@lru_cache
def client_par_defaut() -> ClientLLM:
    return ClientOpenAICompatible()
