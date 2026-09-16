"""Indexe les documents de l'entreprise dans Qdrant.

    uv run python -m exemplia.rag.indexer              # met l'index à jour
    uv run python -m exemplia.rag.indexer --reconstruire

Par défaut, seuls les passages nouveaux ou modifiés sont vectorisés et ceux qui ont disparu des
documents sont retirés. `--reconstruire` repart d'un index vide, utile après un changement de
modèle d'embeddings ou de découpage.
"""

import argparse

from exemplia.rag.decoupage import decouper
from exemplia.rag.index import index_par_defaut
from exemplia.socle.documents import charger_documents


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reconstruire", action="store_true")
    args = parser.parse_args()

    passages = [p for doc in charger_documents() for p in decouper(doc)]
    index = index_par_defaut()
    if args.reconstruire:
        print(f"{index.indexer(passages)} passages indexés.")
        return
    resultat = index.synchroniser(passages)
    print(
        f"{resultat['ajoutes']} passages indexés, {resultat['inchanges']} inchangés, "
        f"{resultat['supprimes']} supprimés."
    )


if __name__ == "__main__":
    main()
