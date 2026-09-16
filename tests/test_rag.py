import pytest
from qdrant_client import QdrantClient

from exemplia.garde.chaine import garde_standard
from exemplia.rag.decoupage import decouper
from exemplia.rag.index import FauxBm25, IndexHybride, niveaux_autorises
from exemplia.rag.pipeline import RAG, REPONSE_INCONNUE, _nettoyer_citations
from exemplia.socle.documents import Document, charger_documents
from exemplia.socle.llm import FauxClientLLM


@pytest.fixture(scope="module")
def index():
    passages = [p for d in charger_documents() for p in decouper(d)]
    idx = IndexHybride(QdrantClient(":memory:"), FauxClientLLM(dimension=64), FauxBm25())
    idx.indexer(passages)
    return idx


def test_decoupage_par_section():
    doc = Document(
        "d", "Titre", "public", "# Titre\n\n## A\n\nun\n\n## B\n\n" + "\n\n".join(["x" * 400] * 3)
    )
    passages = decouper(doc, taille_max=900)
    assert [p.section for p in passages] == ["A", "B", "B (suite)"]
    assert passages[2].texte.startswith("x" * 400)  # chevauchement d'un paragraphe
    assert passages[0].texte_indexe.startswith("Titre — A")


def test_tous_les_documents_decoupes():
    for doc in charger_documents():
        assert decouper(doc), doc.nom


def test_niveaux_autorises():
    assert niveaux_autorises("public") == ["public"]
    assert niveaux_autorises("confidentiel") == ["public", "interne", "confidentiel"]


@pytest.mark.parametrize("niveau", ["public", "interne", "confidentiel"])
def test_filtre_acces_dans_la_recherche(index, niveau):
    resultats = index.rechercher("contrat délai de paiement fournisseur", niveau, k=50)
    assert resultats
    assert {p.acces for p, _ in resultats} <= set(niveaux_autorises(niveau))


def test_recherche_pertinente(index):
    resultats = index.rechercher("retourner un produit délai 30 jours", "public", k=5)
    assert any(p.document == "politique-de-retour" for p, _ in resultats[:3])


def test_citations_nettoyees():
    texte, cites = _nettoyer_citations("A [1]. B [2, 7]. C [9].", nb_sources=3)
    assert texte == "A [1]. B [2]. C ."
    assert cites == [1, 2]


def test_reponse_avec_sources(index):
    client = FauxClientLLM(["Vous avez 30 jours après la livraison [1]."])
    rag = RAG(client, index, garde_standard(masquer_donnees_personnelles=False), k_final=3)
    reponse = rag.repondre("Combien de temps pour retourner un produit ?", "public")
    assert reponse.sources and len(reponse.sources) == 1
    prompt = client.appels[0]["messages"][1]["content"]
    assert '<source numero="1">' in prompt and '<source numero="4">' not in prompt


def test_seuil_rerank_sans_passage(index):
    class RerankerSevere:
        def scorer(self, question, textes):
            return [0.0] * len(textes)

    client = FauxClientLLM()
    rag = RAG(client, index, garde_standard(), reranker=RerankerSevere(), seuil_rerank=0.5)
    reponse = rag.repondre("Quel est le chiffre d'affaires ?", "public")
    assert reponse.texte == REPONSE_INCONNUE
    assert not client.appels


def test_non_reponse_non_bloquee_par_la_garde(index):
    """« Je ne trouve pas… » figure dans le prompt système : le contrôle de fuite doit l'ignorer."""
    rag = RAG(FauxClientLLM([REPONSE_INCONNUE]), index, garde_standard())
    reponse = rag.repondre("Quel est le chiffre d'affaires de l'entreprise ?", "public")
    assert reponse.texte == REPONSE_INCONNUE and not reponse.bloquee


def test_synchronisation_incrementale():
    """Seuls les passages nouveaux ou modifiés sont vectorisés ; les disparus sont supprimés."""
    doc = Document("d", "Titre", "public", "# Titre\n\n## A\n\nun\n\n## B\n\ndeux")
    client = FauxClientLLM(dimension=64)
    index = IndexHybride(QdrantClient(":memory:"), client, FauxBm25(), collection="sync")
    assert index.synchroniser(decouper(doc)) == {"ajoutes": 2, "inchanges": 0, "supprimes": 0}

    appels = len(client.appels)
    assert index.synchroniser(decouper(doc)) == {"ajoutes": 0, "inchanges": 2, "supprimes": 0}
    assert len(client.appels) == appels  # aucun embedding recalculé

    # Une section modifiée, une supprimée, une ajoutée : les sections intactes ne bougent pas.
    modifie = Document(
        "d", "Titre", "public", "# Titre\n\n## A\n\nun corrigé\n\n## B\n\ndeux\n\n## C\n\ntrois"
    )
    assert index.synchroniser(decouper(modifie)) == {
        "ajoutes": 2,
        "inchanges": 1,
        "supprimes": 0,
    }
    sans_b = Document("d", "Titre", "public", "# Titre\n\n## A\n\nun corrigé\n\n## C\n\ntrois")
    assert index.synchroniser(decouper(sans_b)) == {
        "ajoutes": 0,
        "inchanges": 2,
        "supprimes": 1,
    }
    sections = {p.section for p, _ in index.rechercher("un corrigé", "public", k=10)}
    assert sections == {"A", "C"}
