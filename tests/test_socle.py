from types import SimpleNamespace

from pydantic import BaseModel
from sqlalchemy import func, select

from exemplia.socle import base_donnees as bd
from exemplia.socle import entreprise
from exemplia.socle.llm import (
    AppelOutil,
    ClientOpenAICompatible,
    FauxClientLLM,
    ReponseLLM,
    message_outil,
)
from tests.conftest import DATE_REFERENCE


def test_generation_deterministe():
    a = entreprise.generer(DATE_REFERENCE)
    b = entreprise.generer(DATE_REFERENCE)
    assert a.commandes == b.commandes
    assert a.tickets == b.tickets
    assert len(a.clients) == 20 and len(a.commandes) == 60 and len(a.tickets) == 300


def test_coherence_des_commandes():
    d = entreprise.generer(DATE_REFERENCE)
    for c in d.commandes:
        lignes = [lg for lg in d.lignes_commande if lg["commande_id"] == c["id"]]
        assert lignes
        assert c["montant"] == sum(lg["prix_unitaire"] * lg["quantite"] for lg in lignes)
        if c["statut"] in ("en_preparation", "expediee", "annulee"):
            assert c["date_livraison"] is None
        else:
            assert c["date_livraison"] is not None
    statuts = {c["statut"] for c in d.commandes}
    assert {"en_preparation", "livree"} <= statuts


def test_categories_equilibrees():
    d = entreprise.generer(DATE_REFERENCE)
    for categorie in entreprise.CATEGORIES_TICKETS:
        assert sum(t["categorie"] == categorie for t in d.tickets) == 60


def test_chargement(moteur_entreprise):
    with moteur_entreprise.connect() as cx:
        assert cx.scalar(select(func.count()).select_from(bd.commandes)) == 60


def test_faux_client_scenario():
    class Sortie(BaseModel):
        valeur: int

    appel = AppelOutil(id="1", nom="outil", arguments={"x": 1})
    client = FauxClientLLM([ReponseLLM(appels_outils=[appel]), "fin", Sortie(valeur=3)])
    r = client.discuter([{"role": "user", "content": "?"}])
    assert r.appels_outils[0].nom == "outil"
    assert r.message()["tool_calls"][0]["function"]["name"] == "outil"
    assert message_outil(appel, {"ok": True})["tool_call_id"] == "1"
    assert client.discuter([]).texte == "fin"
    assert client.extraire([], Sortie).valeur == 3


def test_vecteurs_factices_proches():
    client = FauxClientLLM()
    a, b, c = client.vectoriser(["retour produit", "retour du produit", "facture abonnement"])

    def cos(u, v):
        return sum(x * y for x, y in zip(u, v, strict=True))

    assert cos(a, b) > cos(a, c)


class _CompletionsEnregistrees:
    def __init__(self, contenu: str) -> None:
        self.contenu = contenu
        self.appels: list[dict] = []

    def create(self, **kwargs):
        self.appels.append(kwargs)
        message = SimpleNamespace(content=self.contenu, tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _client_enregistre(contenu: str, reflexion: str | None) -> tuple[ClientOpenAICompatible, list]:
    client = ClientOpenAICompatible(base_url="http://localhost:1/v1", reflexion=reflexion)
    completions = _CompletionsEnregistrees(contenu)
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return client, completions.appels


def test_client_openai_reflexion_et_balises():
    client, appels = _client_enregistre("<think>calcul</think> 51", reflexion="none")
    assert client.discuter([{"role": "user", "content": "17*3"}]).texte == "51"
    assert appels[0]["reasoning_effort"] == "none"

    client, appels = _client_enregistre("51", reflexion="")
    client.discuter([{"role": "user", "content": "17*3"}])
    assert "reasoning_effort" not in appels[0]


def test_client_openai_extraire_avec_reflexion():
    class Sortie(BaseModel):
        valeur: int

    client, appels = _client_enregistre('{"valeur": 3}', reflexion="low")
    assert client.extraire([], Sortie).valeur == 3
    assert appels[0]["reasoning_effort"] == "low"
    assert appels[0]["response_format"]["type"] == "json_schema"
