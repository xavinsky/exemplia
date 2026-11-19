# Comment utiliser ?

## Lancer

```bash
docker compose up -d qdrant
uv run python -m exemplia.rag.indexer                 # met l'index à jour
uv run python -m exemplia.rag.indexer --reconstruire  # repart d'un index vide
uv run exemplia                                       # page /rag
```

Par défaut, l'indexation est incrémentale : elle ne vectorise que les passages nouveaux ou modifiés
et retire ceux qui ont disparu des documents (`synchroniser`). `--reconstruire` sert après un
changement de modèle d'embeddings ou de découpage, qui rend l'index existant incohérent.

La page propose des questions d'exemple. Poser la question sur le geste commercial en `public` puis
en `interne` montre le filtrage : la réponse n'est disponible qu'au niveau interne. La table des
passages récupérés affiche les scores de fusion et de reranking.

## Fichiers

| Fichier | Contenu |
|---|---|
| `decoupage.py` | Découpage en passages |
| `index.py` | Index hybride Qdrant, encodeurs BM25, reranker |
| `pipeline.py` | Garde, sélection, génération citée |
| `indexer.py` | Script d'indexation |
| `web.py`, `templates/` | Interface |
